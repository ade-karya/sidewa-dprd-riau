"""Drive Humas di Hugging Face S3 melalui rclone.

Setiap pengguna punya ruang pribadi di ``<SIDEWA_HF_S3_PREFIX>/drive/pribadi/<id>/``
dengan kuota ``SIDEWA_DRIVE_QUOTA_GB`` (default 100 GB). Area bersama tim tetap
tersedia di akar ``drive/`` sehingga berkas lama tidak perlu dipindahkan.

Semua operasi (daftar, unggah, unduh, ubah nama, hapus) memakai rclone; tidak
ada metadata tambahan di database.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import settings
from ..utils import format_datetime_id
from . import media_sync

logger = logging.getLogger("sidewa.drive")

ROOT_DIR = "drive"
PERSONAL_DIR = "pribadi"
PLACEHOLDER = ".keep"
MAX_NAME_LENGTH = 120
MAX_SEARCH_RESULTS = 120
USAGE_TTL = 60.0

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_usage_lock = threading.Lock()
_usage_cache: dict[str, tuple[float, int]] = {}


class DriveError(RuntimeError):
    """Kesalahan yang aman ditampilkan ke pengguna."""


class DriveUnavailable(DriveError):
    """Drive belum siap (rclone/HF S3 belum dikonfigurasi)."""


class DriveQuotaExceeded(DriveError):
    """Berkas tidak muat dalam sisa kuota pengguna."""


def available() -> bool:
    return bool(
        settings.drive_enabled
        and settings.hf_s3_configured
        and media_sync.binary_path() is not None
    )


# ─────────────────────────────────────────────────────────────────────────────
# Path & nama
# ─────────────────────────────────────────────────────────────────────────────


def clean_name(name: str) -> str:
    """Rapikan satu segmen nama berkas/folder agar aman dipakai di S3."""
    value = _CONTROL.sub("", (name or "").replace("/", "-").replace("\\", "-")).strip()
    value = re.sub(r"\s+", " ", value).strip(". ")
    if not value or value in {".", ".."}:
        raise DriveError("Nama berkas tidak valid.")
    if len(value) > MAX_NAME_LENGTH:
        stem, dot, extension = value.rpartition(".")
        if dot and 0 < len(extension) <= 12:
            value = f"{stem[: MAX_NAME_LENGTH - len(extension) - 1]}.{extension}"
        else:
            value = value[:MAX_NAME_LENGTH]
    return value


def normalize_dir(path: str | None) -> str:
    """Validasi path folder relatif terhadap akar Drive."""
    raw = (path or "").replace("\\", "/")
    segments: list[str] = []
    for part in raw.split("/"):
        segment = part.strip()
        if not segment or segment == ".":
            continue
        if segment == "..":
            raise DriveError("Folder tidak valid.")
        segments.append(clean_name(segment))
    return "/".join(segments)


def validate_path(path: str | None) -> str:
    """Validasi path yang sudah ada tanpa mengubah nama berkas."""
    raw = (path or "").replace("\\", "/")
    segments: list[str] = []
    for part in raw.split("/"):
        segment = part.strip()
        if not segment or segment == ".":
            continue
        if segment == ".." or _CONTROL.search(segment):
            raise DriveError("Path tidak valid.")
        segments.append(segment)
    return "/".join(segments)


def personal_root(user_id: int) -> str:
    """Akar Drive pribadi satu pengguna."""
    if not user_id or int(user_id) <= 0:
        raise DriveError("Pengguna Drive tidak valid.")
    return f"{PERSONAL_DIR}/{int(user_id)}"


def team_root() -> str:
    """Akar Drive bersama tim (isi lama tetap di tempatnya)."""
    return ""


def _join(directory: str, name: str) -> str:
    directory = normalize_dir(directory)
    return f"{directory}/{name}" if directory else name


def _base() -> str:
    return f"{media_sync.rclone_root()}/{ROOT_DIR}"


def _target(root: str | None, relative_path: str | None = "") -> str:
    parts = [part for part in (validate_path(root), validate_path(relative_path)) if part]
    base = _base()
    return f"{base}/{'/'.join(parts)}" if parts else base


def breadcrumbs(path: str | None, label: str = "Drive") -> list[dict[str, str]]:
    crumbs = [{"label": label, "path": ""}]
    normalized = normalize_dir(path)
    current: list[str] = []
    for segment in normalized.split("/") if normalized else []:
        current.append(segment)
        crumbs.append({"label": segment, "path": "/".join(current)})
    return crumbs


# ─────────────────────────────────────────────────────────────────────────────
# Kuota
# ─────────────────────────────────────────────────────────────────────────────


def quota_bytes() -> int:
    return settings.drive_quota_bytes


def usage(root: str) -> int:
    """Total byte terpakai pada satu akar Drive (pemindaian rekursif rclone)."""
    proc = _run(["size", "--json", _target(root)])
    if proc.returncode != 0:
        raise _fail(proc, "Gagal menghitung pemakaian Drive.")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise DriveError("Balasan rclone tidak dapat dibaca.") from exc
    return int(data.get("bytes") or 0)


def usage_cached(root: str, ttl: float = USAGE_TTL) -> int:
    """Pemakaian dengan cache singkat agar halaman tidak memindai S3 terus-menerus."""
    now = time.monotonic()
    with _usage_lock:
        cached = _usage_cache.get(root)
        if cached and now - cached[0] < ttl:
            return cached[1]
    value = usage(root)
    with _usage_lock:
        _usage_cache[root] = (now, value)
    return value


def forget_usage(root: str) -> None:
    with _usage_lock:
        _usage_cache.pop(root, None)


def quota_state(root: str, cached: bool = True) -> dict[str, Any]:
    """Ringkasan kuota untuk ditampilkan di halaman Drive."""
    total = quota_bytes()
    used = usage_cached(root) if cached else usage(root)
    remaining = max(0, total - used)
    percent = 0.0 if total <= 0 else min(100.0, used / total * 100)
    return {
        "used": used,
        "total": total,
        "remaining": remaining,
        "percent": round(percent, 1),
        "used_percent": int(percent),
        "full": used >= total,
        "warning": percent >= 90,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Primitif rclone
# ─────────────────────────────────────────────────────────────────────────────


def _run(args: list[str], timeout: int | None = None):
    if not available():
        raise DriveUnavailable("Drive belum dikonfigurasi (rclone/HF S3).")
    try:
        proc = media_sync.rclone_run(args, timeout=timeout)
    except media_sync.RcloneError as exc:
        raise DriveError(str(exc)) from exc
    return proc


def _fail(proc, message: str = "Operasi Drive gagal.") -> DriveError:
    detail = media_sync.rclone_error(proc)
    logger.warning("Drive: %s (%s)", message, detail)
    return DriveError(f"{message} {detail}".strip())


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _entries(root: str, directory: str) -> list[dict[str, Any]]:
    proc = _run(["lsjson", "--max-depth", "1", _target(root, directory)])
    if proc.returncode != 0:
        raise _fail(proc, "Gagal membaca folder.")
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise DriveError("Balasan rclone tidak dapat dibaca.") from exc

    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("Name") or "")
        if not name or name == PLACEHOLDER:
            continue
        # Folder penyimpanan pribadi tidak ditampilkan pada akar Drive tim.
        if not root and not directory and name == PERSONAL_DIR:
            continue
        item = {
            "name": name,
            "path": _join(directory, name),
            "is_dir": bool(row.get("IsDir")),
            "size": int(row.get("Size") or 0),
            "modified": None,
            "modified_label": "—",
        }
        if not item["is_dir"]:
            modified = _parse_time(row.get("ModTime"))
            item["modified"] = modified
            item["modified_label"] = format_datetime_id(modified) if modified else "—"
        (folders if item["is_dir"] else files).append(item)

    folders.sort(key=lambda entry: entry["name"].casefold())
    files.sort(key=lambda entry: entry["name"].casefold())
    return folders + files


def listing(root: str, path: str | None, label: str = "Drive") -> dict[str, Any]:
    directory = normalize_dir(path)
    entries = _entries(root, directory)
    file_count = sum(1 for entry in entries if not entry["is_dir"])
    return {
        "path": directory,
        "entries": entries,
        "crumbs": breadcrumbs(directory, label),
        "folder_count": len(entries) - file_count,
        "file_count": file_count,
        "total_size": sum(entry["size"] for entry in entries if not entry["is_dir"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Operasi berkas
# ─────────────────────────────────────────────────────────────────────────────


def _exists(root: str, relative_path: str) -> bool:
    proc = _run(["lsf", "--max-depth", "1", _target(root, relative_path)])
    if proc.returncode != 0:
        raise _fail(proc, "Gagal memeriksa folder.")
    return bool((proc.stdout or "").strip())


def _unique_name(root: str, directory: str, name: str) -> str:
    taken = {entry["name"] for entry in _entries(root, directory)}
    if name not in taken:
        return name
    stem, dot, extension = name.rpartition(".")
    base, suffix = (stem, f".{extension}") if dot and extension else (name, "")
    index = 2
    while f"{base} ({index}){suffix}" in taken:
        index += 1
    return f"{base} ({index}){suffix}"


def upload_file(root: str, directory: str, filename: str, source: str | Path) -> str:
    directory = normalize_dir(directory)
    name = clean_name(os.path.basename(filename))
    name = _unique_name(root, directory, name)
    target = _target(root, _join(directory, name))
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    proc = _run(
        [
            "copyto",
            str(source),
            target,
            "--s3-no-check-bucket",
            "--header-upload",
            f"Content-Type: {mime}",
        ]
    )
    if proc.returncode != 0:
        raise _fail(proc, f"Gagal mengunggah {name}.")
    forget_usage(root)
    return name


def create_folder(root: str, directory: str, name: str) -> str:
    directory = normalize_dir(directory)
    name = clean_name(name)
    relative = _join(directory, name)
    if _exists(root, relative):
        raise DriveError(f"Folder “{name}” sudah ada.")
    # S3 tidak menyimpan folder kosong; penanda .keep membuat folder tetap tampil.
    with tempfile.NamedTemporaryFile(prefix="sidewa-drive-", delete=False) as placeholder:
        placeholder_path = Path(placeholder.name)
    try:
        proc = _run(
            [
                "copyto",
                str(placeholder_path),
                f"{_target(root, relative)}/{PLACEHOLDER}",
                "--s3-no-check-bucket",
                "--header-upload",
                "Content-Type: application/x-empty",
            ]
        )
    finally:
        placeholder_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise _fail(proc, f"Gagal membuat folder {name}.")
    forget_usage(root)
    return relative


def delete_entry(root: str, path: str, is_dir: bool) -> str:
    relative = validate_path(path)
    if not relative:
        raise DriveError("Folder akar Drive tidak dapat dihapus.")
    if is_dir:
        proc = _run(["purge", _target(root, relative)])
    else:
        proc = _run(["deletefile", _target(root, relative)])
    if proc.returncode == 0:
        forget_usage(root)
        return relative
    error = media_sync.rclone_error(proc)
    if not is_dir and (proc.returncode == 4 or "not found" in error.lower()):
        forget_usage(root)
        return relative
    raise DriveError(f"Gagal menghapus {relative.rsplit('/', 1)[-1]}. {error}".strip())


def rename_entry(root: str, path: str, new_name: str, is_dir: bool) -> str:
    relative = validate_path(path)
    if not relative:
        raise DriveError("Folder akar Drive tidak dapat diubah namanya.")
    parent, _, current = relative.rpartition("/")
    name = clean_name(new_name)
    if name == current:
        return relative
    destination = f"{parent}/{name}" if parent else name
    if _exists(root, destination):
        raise DriveError(f"Nama “{name}” sudah dipakai.")
    proc = _run(["moveto", _target(root, relative), _target(root, destination)])
    if proc.returncode != 0:
        raise _fail(proc, f"Gagal mengubah nama {current}.")
    forget_usage(root)
    return destination


def download_file(root: str, path: str) -> tuple[str, str, str]:
    """Unduh berkas ke berkas sementara; kembalikan (path, nama, mime)."""
    relative = validate_path(path)
    if not relative:
        raise DriveError("Berkas tidak ditemukan.")
    name = relative.rsplit("/", 1)[-1]
    handle, temporary = tempfile.mkstemp(prefix="sidewa-drive-", suffix=".part")
    os.close(handle)
    proc = _run(["copyto", _target(root, relative), temporary, "--s3-no-check-bucket"])
    if proc.returncode != 0:
        Path(temporary).unlink(missing_ok=True)
        raise _fail(proc, f"Gagal mengunduh {name}.")
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    # Jangan pernah biarkan browser merender HTML/SVG dari Drive.
    if mime in {"text/html", "image/svg+xml", "application/xhtml+xml"}:
        mime = "application/octet-stream"
    return temporary, name, mime


def search(root: str, query: str) -> dict[str, Any]:
    term = (query or "").strip()
    if not term:
        return {"query": "", "results": [], "truncated": False}
    proc = _run(["lsf", "-R", "--files-only", "--format", "p", _target(root)])
    if proc.returncode != 0:
        raise _fail(proc, "Gagal mencari berkas.")
    lowered = term.casefold()
    results = []
    truncated = False
    for line in (proc.stdout or "").splitlines():
        try:
            relative = validate_path(line)
        except DriveError:
            continue
        if not relative or relative.rsplit("/", 1)[-1] == PLACEHOLDER:
            continue
        # Drive tim tidak boleh menampilkan berkas dari ruang pribadi.
        if not root and relative.split("/", 1)[0] == PERSONAL_DIR:
            continue
        if lowered not in relative.casefold():
            continue
        if len(results) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        name = relative.rsplit("/", 1)[-1]
        folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
        results.append(
            {
                "name": name,
                "path": relative,
                "folder": folder,
                "is_dir": False,
                "size": 0,
                "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
            }
        )
    return {"query": term, "results": results, "truncated": truncated}
