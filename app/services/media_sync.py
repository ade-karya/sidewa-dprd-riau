"""Sinkronisasi media ke Hugging Face S3 (S3-compatible).

PostgreSQL lokal hanya cache. Setiap berkas media yang ditulis aplikasi
diunggah ke bucket HF S3. Jika cache lokal hilang, berkas diunduh kembali
saat pertama kali diminta (on-demand cache).
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
from .images import absolute_path

logger = logging.getLogger("sidewa.media_sync")

_client = None
_client_lock = threading.Lock()
_bucket_checked = False


def _enabled() -> bool:
    return bool(
        settings.media_sync_enabled
        and settings.hf_s3_configured
        and settings.database_url.startswith("postgresql")
    )


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            import boto3
            from botocore.config import Config
        except ImportError:  # pragma: no cover - dependensi produksi
            logger.error("boto3 tidak terpasang; sinkronisasi media dinonaktifkan.")
            return None
        _client = boto3.client(
            "s3",
            endpoint_url=settings.hf_s3_endpoint,
            region_name=settings.hf_s3_region,
            aws_access_key_id=settings.hf_s3_access_key_id,
            aws_secret_access_key=settings.hf_s3_secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )
        return _client


def _key(relative_path: str) -> str:
    prefix = settings.hf_s3_prefix.strip("/")
    path = relative_path.lstrip("/")
    return f"{prefix}/{path}" if prefix else path


def ensure_bucket() -> bool:
    """Pastikan bucket HF S3 dapat diakses (bucket tidak dibuat otomatis)."""
    global _bucket_checked
    if _bucket_checked:
        return True
    client = _get_client()
    if client is None:
        return False
    try:
        client.head_bucket(Bucket=settings.hf_s3_bucket)
        _bucket_checked = True
        return True
    except Exception as exc:
        logger.warning(
            "Bucket HF S3 '%s' belum dapat diakses: %s", settings.hf_s3_bucket, exc
        )
        return False


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
    client = _get_client()
    if client is None:
        return False
    try:
        local = absolute_path(relative_path)
        if not local.is_file():
            return False
        content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        client.upload_file(
            Filename=str(local),
            Bucket=settings.hf_s3_bucket,
            Key=_key(relative_path),
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as exc:
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
    _scan()
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
    client = _get_client()
    if client is None:
        return False
    try:
        client.delete_object(Bucket=settings.hf_s3_bucket, Key=_key(relative_path))
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code not in {"404", "NoSuchKey", "NotFound"}:
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
    client = _get_client()
    if client is None:
        return False

    local.parent.mkdir(parents=True, exist_ok=True)
    temporary = local.with_name(f".{local.name}.{uuid4().hex}.part")
    try:
        client.download_file(
            Bucket=settings.hf_s3_bucket,
            Key=_key(relative_path),
            Filename=str(temporary),
        )
        os.replace(temporary, local)
    except Exception as exc:
        logger.warning("Unduh media %s dari HF S3 gagal: %s", relative_path, exc)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    _mark_uploaded(relative_path, local)
    return True


def status() -> dict[str, Any]:
    if not _enabled():
        return {"enabled": False}
    try:
        with engine.connect() as conn:
            pending = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM media_sync WHERE uploaded_at IS NULL")
                ).scalar()
                or 0
            )
            failed = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM media_sync WHERE attempts > 0")
                ).scalar()
                or 0
            )
            deletions = int(
                conn.execute(text("SELECT COUNT(*) FROM media_sync_deletions")).scalar() or 0
            )
        return {
            "enabled": True,
            "pending": pending,
            "failed": failed,
            "pending_deletions": deletions,
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}
