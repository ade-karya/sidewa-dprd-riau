"""Sinkronisasi media ke Hugging Face S3 lewat boto3 (S3 native).

Setiap berkas media yang ditulis aplikasi dicatat di antrean ``media_sync``
(PostgreSQL/Supabase) lalu diunggah langsung ke bucket HF S3 oleh worker
latar belakang. Jika cache lokal hilang, berkas diunduh kembali saat pertama
kali diminta (*on-demand cache*).

Tidak ada biner eksternal: endpoint, kredensial, dan *path-style addressing*
dibangun dari variabel ``SIDEWA_HF_S3_*`` di :mod:`app.services.s3`.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from ..config import settings
from ..database import engine
from . import s3
from .images import absolute_path

logger = logging.getLogger("sidewa.media_sync")

_bucket_checked = False

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_stop = threading.Event()


class MediaSyncError(RuntimeError):
    """Kegagalan operasi media di HF S3."""


def _enabled() -> bool:
    return bool(
        settings.media_sync_enabled
        and settings.hf_s3_configured
        and settings.database_url.startswith("postgresql")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Path S3
# ─────────────────────────────────────────────────────────────────────────────


def _prefix() -> str:
    return settings.hf_s3_prefix.strip("/")


def _root_prefix() -> str:
    prefix = _prefix()
    return f"{prefix}/" if prefix else ""


def _key(relative_path: str) -> str:
    prefix = _prefix()
    path = relative_path.lstrip("/")
    return f"{prefix}/{path}" if prefix else path


def ensure_bucket() -> bool:
    """Pastikan bucket HF S3 dapat dibaca (bucket tidak dibuat otomatis)."""
    global _bucket_checked
    if _bucket_checked:
        return True
    if not settings.hf_s3_configured:
        return False
    try:
        s3.ping(_root_prefix() or None)
    except s3.S3Error as exc:
        logger.warning("HF S3 tidak dapat diakses: %s", exc)
        return False
    _bucket_checked = True
    return True


def check() -> dict[str, Any]:
    """Diagnosa koneksi langsung ke HF S3 (dipakai ``python -m app.cli media-check``)."""
    report: dict[str, Any] = {
        "backend": "boto3",
        "endpoint": settings.hf_s3_endpoint,
        "bucket": settings.hf_s3_bucket,
        "prefix": settings.hf_s3_prefix,
        "configured": settings.hf_s3_configured,
        "enabled": _enabled(),
        "ok": False,
    }
    if not settings.hf_s3_configured:
        report["error"] = "HF S3 belum dikonfigurasi (SIDEWA_HF_S3_*)"
        return report
    try:
        info = s3.ping(_root_prefix() or None)
    except s3.S3Error as exc:
        report["error"] = str(exc)
        return report
    report.update({"ok": True, **info})
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Antrean lokal
# ─────────────────────────────────────────────────────────────────────────────


def enqueue_upload(relative_path: str) -> None:
    if not _enabled() or not relative_path:
        return
    try:
        local = absolute_path(relative_path)
        if not local.is_file():
            return
        stat = local.stat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO media_sync (path, size, mtime, uploaded_at, attempts) "
                    "VALUES (:path, :size, :mtime, NULL, 0) "
                    "ON CONFLICT (path) DO UPDATE SET "
                    "size = EXCLUDED.size, mtime = EXCLUDED.mtime, "
                    "uploaded_at = NULL, attempts = 0"
                ),
                {
                    "path": relative_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                },
            )
    except Exception:
        logger.exception("Gagal memasukkan media ke antrean: %s", relative_path)


def enqueue_delete(relative_path: str) -> None:
    if not _enabled() or not relative_path:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO media_sync_deletions (path) VALUES (:path) "
                    "ON CONFLICT (path) DO NOTHING"
                ),
                {"path": relative_path},
            )
            conn.execute(
                text("DELETE FROM media_sync WHERE path = :path"),
                {"path": relative_path},
            )
    except Exception:
        logger.exception("Gagal memasukkan media ke antrean hapus: %s", relative_path)


def _mark_uploaded(relative_path: str, local: Path) -> None:
    try:
        stat = local.stat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO media_sync "
                    "(path, size, mtime, uploaded_at, attempts, last_error) "
                    "VALUES (:path, :size, :mtime, now(), 0, NULL) "
                    "ON CONFLICT (path) DO UPDATE SET "
                    "size = EXCLUDED.size, mtime = EXCLUDED.mtime, "
                    "uploaded_at = now(), attempts = 0, last_error = NULL"
                ),
                {
                    "path": relative_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                },
            )
    except Exception:
        logger.exception("Gagal menandai media terunggah: %s", relative_path)


def _mark_error(relative_path: str, error: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE media_sync SET attempts = attempts + 1, "
                    "last_error = :error WHERE path = :path"
                ),
                {"error": error[:1000], "path": relative_path},
            )
    except Exception:
        logger.exception("Gagal menandai error media: %s", relative_path)


# ─────────────────────────────────────────────────────────────────────────────
# Pemindaian & unggah
# ─────────────────────────────────────────────────────────────────────────────


def _scan() -> int:
    """Daftarkan berkas lokal baru/berubah ke antrean media_sync."""
    if not _enabled():
        return 0
    root = settings.media_root
    if not root.exists():
        return 0
    files: list[tuple[str, int, float]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime))

    queued = 0
    try:
        with engine.begin() as conn:
            existing = {
                row["path"]: row
                for row in conn.execute(
                    text("SELECT path, size, mtime, uploaded_at FROM media_sync")
                ).mappings()
            }
            for relative_path, size, mtime in files:
                row = existing.get(relative_path)
                changed = (
                    row is None
                    or int(row["size"]) != size
                    or abs(float(row["mtime"]) - mtime) > 0.001
                    or row["uploaded_at"] is None
                )
                if not changed:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO media_sync (path, size, mtime, uploaded_at, attempts) "
                        "VALUES (:path, :size, :mtime, NULL, 0) "
                        "ON CONFLICT (path) DO UPDATE SET "
                        "size = EXCLUDED.size, mtime = EXCLUDED.mtime, "
                        "uploaded_at = NULL, attempts = 0"
                    ),
                    {"path": relative_path, "size": size, "mtime": mtime},
                )
                queued += 1
    except Exception:
        logger.exception("Gagal memindai media lokal")
        return 0
    return queued


def upload_path(relative_path: str) -> bool:
    if not _enabled():
        return False
    try:
        local = absolute_path(relative_path)
    except ValueError:
        return False
    if not local.is_file():
        return False
    content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
    try:
        s3.put_file(
            settings.hf_s3_bucket,
            _key(relative_path),
            local,
            content_type=content_type,
        )
    except s3.S3Error as exc:
        logger.warning("Upload media %s ke HF S3 gagal: %s", relative_path, exc)
        _mark_error(relative_path, str(exc))
        return False
    _mark_uploaded(relative_path, local)
    return True


def _upload_pending(limit: int) -> int:
    try:
        with engine.connect() as conn:
            paths = (
                conn.execute(
                    text(
                        "SELECT path FROM media_sync WHERE uploaded_at IS NULL "
                        "ORDER BY attempts ASC, path ASC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .scalars()
                .all()
            )
    except Exception:
        logger.exception("Gagal membaca antrean media")
        return 0
    uploaded = 0
    for path in paths:
        if upload_path(path):
            uploaded += 1
    return uploaded


def sync_pending(limit: int = 20) -> int:
    if not _enabled():
        return 0
    ensure_bucket()
    return _upload_pending(limit)


def sync_all() -> int:
    if not _enabled():
        return 0
    ensure_bucket()
    _scan()
    total = 0
    while True:
        uploaded = _upload_pending(100)
        total += uploaded
        if uploaded == 0:
            break
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Hapus & unduh on-demand
# ─────────────────────────────────────────────────────────────────────────────


def delete_remote(relative_path: str) -> bool:
    if not _enabled():
        return False
    try:
        s3.delete_object(settings.hf_s3_bucket, _key(relative_path))
    except s3.S3Error as exc:
        logger.warning("Hapus media %s dari HF S3 gagal: %s", relative_path, exc)
        return False
    return True


def process_deletions(limit: int = 20) -> int:
    if not _enabled():
        return 0
    try:
        with engine.connect() as conn:
            paths = (
                conn.execute(
                    text(
                        "SELECT path FROM media_sync_deletions "
                        "ORDER BY queued_at ASC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .scalars()
                .all()
            )
    except Exception:
        logger.exception("Gagal membaca antrean hapus media")
        return 0

    deleted = 0
    for path in paths:
        if not delete_remote(path):
            break
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM media_sync_deletions WHERE path = :path"),
                {"path": path},
            )
            conn.execute(text("DELETE FROM media_sync WHERE path = :path"), {"path": path})
        deleted += 1
    return deleted


def download_to_cache(relative_path: str) -> bool:
    """Unduh berkas dari HF S3 ke cache lokal bila belum ada."""
    if not _enabled():
        return False
    try:
        local = absolute_path(relative_path)
    except ValueError:
        return False
    if local.is_file():
        return True

    local.parent.mkdir(parents=True, exist_ok=True)
    temporary = local.with_name(f".{local.name}.{uuid4().hex}.part")
    try:
        s3.download_file(settings.hf_s3_bucket, _key(relative_path), temporary)
        os.replace(temporary, local)
    except (s3.S3Error, OSError) as exc:
        logger.warning("Unduh media %s dari HF S3 gagal: %s", relative_path, exc)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    _mark_uploaded(relative_path, local)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Worker latar belakang
# ─────────────────────────────────────────────────────────────────────────────


def _run_worker() -> None:
    while not _stop.is_set():
        try:
            if _enabled():
                sync_pending(limit=20)
                process_deletions(limit=20)
        except Exception:
            logger.exception("Siklus sinkronisasi media HF S3 gagal")
        _stop.wait(max(5, settings.media_sync_interval))


def start_worker() -> None:
    global _worker
    if not (settings.media_sync_enabled and settings.hf_s3_configured):
        return
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        _stop.clear()
        _worker = threading.Thread(
            target=_run_worker, name="sidewa-media-sync", daemon=True
        )
        _worker.start()
        logger.info(
            "Worker media HF S3 aktif (interval=%ss).", settings.media_sync_interval
        )


def stop_worker() -> None:
    global _worker
    with _worker_lock:
        thread = _worker
        _worker = None
    if thread is None:
        return
    _stop.set()
    thread.join(timeout=10)


def status() -> dict[str, Any]:
    backend = {
        "backend": "boto3",
        "endpoint": settings.hf_s3_endpoint,
        "bucket": settings.hf_s3_bucket,
        "prefix": settings.hf_s3_prefix,
    }
    if not _enabled():
        return {"enabled": False, **backend}
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM media_sync WHERE uploaded_at IS NULL), "
                    "(SELECT COUNT(*) FROM media_sync WHERE attempts > 0), "
                    "(SELECT COUNT(*) FROM media_sync_deletions)"
                )
            ).one()
        pending, failed, deletions = (int(value or 0) for value in row)
        return {
            "enabled": True,
            "pending": pending,
            "failed": failed,
            "pending_deletions": deletions,
            **backend,
        }
    except Exception as exc:
        return {"enabled": True, **backend, "error": str(exc)}
