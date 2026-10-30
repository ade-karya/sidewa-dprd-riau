"""Sinkronisasi media ke Hugging Face S3 lewat rclone (S3 native).

PostgreSQL lokal hanya cache. Setiap berkas media yang ditulis aplikasi
diunggah ke bucket HF S3 memakai perintah ``rclone``. Jika cache lokal hilang,
berkas diunduh kembali saat pertama kali diminta (on-demand cache).

Remote rclone tidak perlu ditulis di ``rclone.conf``: konfigurasi S3 dibangun
dari variabel ``SIDEWA_HF_S3_*`` dan disuntikkan sebagai environment
``RCLONE_CONFIG_<REMOTE>_*``. Endpoint HF (``https://s3.hf.co/<namespace>``)
dipakai apa adanya dengan path-style addressing.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from ..config import settings
from ..database import engine
from .images import absolute_path

logger = logging.getLogger("sidewa.media_sync")

_lock = threading.Lock()
_binary_path: str | None = None
_binary_checked = False
_bucket_checked = False


class RcloneError(RuntimeError):
    """Kegagalan menjalankan biner rclone."""


def _enabled() -> bool:
    return bool(
        settings.media_sync_enabled
        and settings.hf_s3_configured
        and settings.database_url.startswith("postgresql")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Konfigurasi remote rclone
# ─────────────────────────────────────────────────────────────────────────────


def _remote_name() -> str:
    raw = (settings.rclone_remote or "sidewahf").strip().rstrip(":")
    # rclone mencocokkan nama remote tanpa membedakan huruf besar/kecil, tetapi
    # karakter selain [A-Za-z0-9_] tidak dinormalisasi. Samakan nama remote
    # dengan nama variabel environment agar keduanya selalu cocok.
    name = "".join(ch if ch.isascii() and (ch.isalnum() or ch == "_") else "_" for ch in raw)
    return name.strip("_") or "sidewahf"


def _env_prefix() -> str:
    # rclone membaca RCLONE_CONFIG_<REMOTE>_<KEY>; nama remote dihuruf-besarkan.
    return f"RCLONE_CONFIG_{_remote_name().upper()}"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    prefix = _env_prefix()
    values = {
        "TYPE": "s3",
        "PROVIDER": "Other",
        "ACCESS_KEY_ID": settings.hf_s3_access_key_id,
        "SECRET_ACCESS_KEY": settings.hf_s3_secret_access_key,
        "ENDPOINT": settings.hf_s3_endpoint,
        "REGION": settings.hf_s3_region or "us-east-1",
        "FORCE_PATH_STYLE": "true",
        # HF S3 belum mengimplementasikan ListObjects v1 (501 NotImplemented).
        "LIST_VERSION": "2",
        "NO_CHECK_BUCKET": "true",
    }
    for key, value in values.items():
        env[f"{prefix}_{key}"] = value
    return env


def binary_path() -> str | None:
    """Lokasi biner rclone, atau ``None`` bila tidak tersedia."""
    global _binary_path, _binary_checked
    with _lock:
        if _binary_checked:
            return _binary_path
        candidate = (settings.rclone_binary or "rclone").strip() or "rclone"
        expanded = os.path.expanduser(candidate)
        found = shutil.which(expanded)
        if not found and os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            found = expanded
        _binary_path = found
        _binary_checked = True
        if found is None:
            logger.error(
                "rclone tidak ditemukan (SIDEWA_RCLONE_BINARY=%s); sinkronisasi media dinonaktifkan.",
                candidate,
            )
        return found


def _root() -> str:
    prefix = settings.hf_s3_prefix.strip("/")
    base = f"{_remote_name()}:{settings.hf_s3_bucket}"
    return f"{base}/{prefix}" if prefix else base


def _key(relative_path: str) -> str:
    prefix = settings.hf_s3_prefix.strip("/")
    path = relative_path.lstrip("/")
    return f"{prefix}/{path}" if prefix else path


def _target(relative_path: str) -> str:
    return f"{_remote_name()}:{settings.hf_s3_bucket}/{_key(relative_path)}"


def _run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    binary = binary_path()
    if binary is None:
        raise RcloneError("biner rclone tidak tersedia")
    command = [binary, "--log-level", "ERROR", *settings.rclone_extra_args, *args]
    try:
        return subprocess.run(
            command,
            env=_env(),
            capture_output=True,
            text=True,
            timeout=timeout or settings.rclone_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RcloneError(
            f"rclone melebihi batas waktu {timeout or settings.rclone_timeout} detik"
        ) from exc
    except OSError as exc:
        raise RcloneError(f"gagal menjalankan rclone: {exc}") from exc


# API publik untuk modul lain (mis. ``drive``) yang juga memakai rclone.
def rclone_run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return _run(args, timeout)


def rclone_root() -> str:
    return _root()


def rclone_error(proc: subprocess.CompletedProcess[str]) -> str:
    return _stderr(proc)


def _stderr(proc: subprocess.CompletedProcess[str]) -> str:
    output = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    if len(output) > 900:
        output = output[-900:]
    return output or f"rclone keluar dengan kode {proc.returncode}"


def _is_missing(output: str) -> bool:
    lowered = output.lower()
    return any(
        marker in lowered
        for marker in ("not found", "doesn't exist", "does not exist", "nosuchkey")
    )


def ensure_bucket() -> bool:
    """Pastikan bucket HF S3 dapat diakses lewat rclone (bucket tidak dibuat otomatis)."""
    global _bucket_checked
    if _bucket_checked:
        return True
    if binary_path() is None:
        return False
    try:
        proc = _run(["lsf", "--max-depth", "1", _root()])
    except RcloneError as exc:
        logger.warning("HF S3 tidak dapat diakses lewat rclone: %s", exc)
        return False
    if proc.returncode == 0:
        _bucket_checked = True
        return True
    logger.warning(
        "Bucket HF S3 '%s' belum dapat diakses lewat rclone: %s",
        settings.hf_s3_bucket,
        _stderr(proc),
    )
    return False


def check() -> dict[str, Any]:
    """Diagnosa koneksi rclone → HF S3 (dipakai ``python -m app.cli media-check``)."""
    binary = binary_path()
    report: dict[str, Any] = {
        "backend": "rclone",
        "binary": binary or settings.rclone_binary,
        "binary_available": binary is not None,
        "remote": _remote_name(),
        "bucket": settings.hf_s3_bucket,
        "prefix": settings.hf_s3_prefix,
        "endpoint": settings.hf_s3_endpoint,
        "configured": settings.hf_s3_configured,
        "enabled": _enabled(),
        "ok": False,
    }
    if not settings.hf_s3_configured:
        report["error"] = "HF S3 belum dikonfigurasi (SIDEWA_HF_S3_*)"
        return report
    if binary is None:
        report["error"] = "biner rclone tidak ditemukan"
        return report
    try:
        version = _run(["version"])
        if version.returncode != 0:
            report["error"] = _stderr(version)
            return report
        report["version"] = (version.stdout or "").splitlines()[0].strip()
        listing = _run(["lsf", "--max-depth", "1", _root()])
    except RcloneError as exc:
        report["error"] = str(exc)
        return report
    report["returncode"] = listing.returncode
    if listing.returncode != 0:
        report["error"] = _stderr(listing)
        return report
    report["ok"] = True
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
    if not _enabled() or binary_path() is None:
        return False
    try:
        local = absolute_path(relative_path)
    except ValueError:
        return False
    if not local.is_file():
        return False
    content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
    try:
        proc = _run(
            [
                "copyto",
                str(local),
                _target(relative_path),
                "--s3-no-check-bucket",
                "--header-upload",
                f"Content-Type: {content_type}",
            ]
        )
    except RcloneError as exc:
        logger.warning("Upload media %s ke HF S3 gagal: %s", relative_path, exc)
        _mark_error(relative_path, str(exc))
        return False
    if proc.returncode != 0:
        error = _stderr(proc)
        logger.warning("Upload media %s ke HF S3 gagal: %s", relative_path, error)
        _mark_error(relative_path, error)
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
    if not _enabled() or binary_path() is None:
        return 0
    ensure_bucket()
    _scan()
    return _upload_pending(limit)


def sync_all() -> int:
    if not _enabled() or binary_path() is None:
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
    if not _enabled() or binary_path() is None:
        return False
    try:
        proc = _run(["deletefile", _target(relative_path)])
    except RcloneError as exc:
        logger.warning("Hapus media %s dari HF S3 gagal: %s", relative_path, exc)
        return False
    if proc.returncode == 0:
        return True
    error = _stderr(proc)
    # ``rclone deletefile`` mengembalikan kode 4 bila objek memang sudah tidak ada.
    if proc.returncode == 4 or _is_missing(error):
        return True
    logger.warning("Hapus media %s dari HF S3 gagal: %s", relative_path, error)
    return False


def process_deletions(limit: int = 20) -> int:
    if not _enabled() or binary_path() is None:
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
    if not _enabled() or binary_path() is None:
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
        proc = _run(
            ["copyto", _target(relative_path), str(temporary), "--s3-no-check-bucket"]
        )
        if proc.returncode != 0:
            raise RcloneError(_stderr(proc))
        os.replace(temporary, local)
    except (RcloneError, OSError) as exc:
        logger.warning("Unduh media %s dari HF S3 gagal: %s", relative_path, exc)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    _mark_uploaded(relative_path, local)
    return True


def status() -> dict[str, Any]:
    backend = {
        "backend": "rclone",
        "remote": _remote_name(),
        "binary": binary_path() or settings.rclone_binary,
        "binary_available": binary_path() is not None,
    }
    if not _enabled():
        return {"enabled": False, **backend}
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
            **backend,
        }
    except Exception as exc:
        return {"enabled": True, **backend, "error": str(exc)}
