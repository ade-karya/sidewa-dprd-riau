"""Drive Humas di Hugging Face S3 melalui boto3 (S3 native).

Setiap pengguna punya ruang pribadi di ``<SIDEWA_HF_S3_PREFIX>/drive/pribadi/<id>/``
dengan kuota ``SIDEWA_DRIVE_QUOTA_GB`` (default 100 GB). Area bersama tim tetap
tersedia di akar ``drive/`` sehingga berkas lama tidak perlu dipindahkan.

Semua operasi (daftar, unggah, unduh, ubah nama, hapus) memakai S3 langsung;
tidak ada metadata tambahan di database dan tidak ada biner eksternal.
"""

from __future__ import annotations

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
from . import s3

logger = logging.getLogger("sidewa.drive")

ROOT_DIR = "drive"
PERSONAL_DIR = "pribadi"
PLACEHOLDER = ".keep"
MAX_NAME_LENGTH = 120
MAX_SEARCH_RESULTS = 120
USAGE_TTL = 60.0
# Masa berlaku tautan unduh langsung (presigned URL) ke HF S3.
LINK_TTL = 1800

# Tipe yang tetap dialirkan lewat server: browser tidak boleh merender HTML/SVG
# dari penyimpanan, dan berkas teks lebih nyaman diunduh sebagai lampiran.
STREAM_INLINE_MIME = frozenset(
    {
        "application/xhtml+xml",
        "image/svg+xml",
        "application/xml",
        "application/json",
    }
)

# Jenis gambar yang aman dipratinjau langsung di browser. SVG sengaja tidak
# dimasukkan karena dapat memuat skrip.
PREVIEW_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/avif",
    }
)


def should_stream(name: str) -> bool:
    """True bila berkas harus dialirkan lewat server, bukan dialihkan ke S3."""
    mime = mimetypes.guess_type(name)[0] or ""
    return mime.startswith("text/") or mime in STREAM_INLINE_MIME


def is_previewable(name: str) -> bool:
    """True bila berkas berupa gambar yang aman ditampilkan sebagai pratinjau."""
    mime = mimetypes.guess_type(name)[0] or ""
    return mime in PREVIEW_MIME


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_usage_lock = threading.Lock()
_usage_cache: dict[str, tuple[float, int]] = {}


class DriveError(RuntimeError):
    """Kesalahan yang aman ditampilkan ke pengguna."""


class DriveUnavailable(DriveError):
    """Drive belum siap (HF S3 belum dikonfigurasi)."""


class DriveQuotaExceeded(DriveError):
    """Berkas tidak muat dalam sisa kuota pengguna."""


def available() -> bool:
    return bool(settings.drive_enabled and settings.hf_s3_configured)


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


def _bucket() -> str:
    """Bucket Drive; dapat dipisah dari bucket media (mis. publik)."""
    return (settings.drive_bucket or settings.hf_s3_bucket).strip()


def _base_prefix() -> str:
    prefix = settings.hf_s3_prefix.strip("/")
    return f"{prefix}/{ROOT_DIR}" if prefix else ROOT_DIR


def _key(root: str | None, relative_path: str | None = "") -> str:
    parts = [_base_prefix()]
    root_part = validate_path(root)
    relative = validate_path(relative_path)
    if root_part:
        parts.append(root_part)
    if relative:
        parts.append(relative)
    return "/".join(part for part in parts if part)


def _folder_prefix(root: str | None, directory: str | None) -> str:
    key = _key(root, directory)
    return f"{key}/" if key else ""


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
    """Total byte terpakai pada satu akar Drive (pemindaian rekursif S3)."""
    try:
        return s3.total_size(_bucket(), _folder_prefix(root, ""))
    except s3.S3Error as exc:
        raise DriveError(f"Gagal menghitung pemakaian Drive. {exc}") from exc


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


def prime_usage(root: str, value: int) -> None:
    """Simpan pemakaian terbaru di cache agar unggahan berurutan tidak memindai S3 tiap berkas."""
    with _usage_lock:
        _usage_cache[root] = (time.monotonic(), max(0, int(value)))


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
# Primitif S3
# ─────────────────────────────────────────────────────────────────────────────


def _require_ready() -> None:
    if not available():
        raise DriveUnavailable("Drive belum dikonfigurasi (HF S3).")


def _entries(root: str, directory: str) -> list[dict[str, Any]]:
    prefix = _folder_prefix(root, directory)
    try:
        objects, folder_prefixes = s3.list_dir(_bucket(), prefix)
    except s3.S3Error as exc:
        raise DriveError(f"Gagal membaca folder. {exc}") from exc

    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for obj in objects:
        key = str(obj.get("Key") or "")
        name = key[len(prefix) :] if prefix and key.startswith(prefix) else key
        if not name or "/" in name or name == PLACEHOLDER:
            continue
        item = {
            "name": name,
            "path": _join(directory, name),
            "is_dir": False,
            "is_image": is_previewable(name),
            "size": int(obj.get("Size") or 0),
            "modified": None,
            "modified_label": "—",
        }
        modified = obj.get("LastModified")
        if isinstance(modified, datetime):
            item["modified"] = modified
            item["modified_label"] = format_datetime_id(modified)
        files.append(item)

    for folder_prefix in folder_prefixes:
        name = folder_prefix[len(prefix) :].rstrip("/") if prefix else folder_prefix.rstrip("/")
        if not name or "/" in name:
            continue
        # Folder penyimpanan pribadi tidak ditampilkan pada akar Drive tim.
        if not root and not directory and name == PERSONAL_DIR:
            continue
        folders.append(
            {
                "name": name,
                "path": _join(directory, name),
                "is_dir": True,
                "is_image": False,
                "size": 0,
                "modified": None,
                "modified_label": "—",
            }
        )

    folders.sort(key=lambda entry: entry["name"].casefold())
    files.sort(key=lambda entry: entry["name"].casefold())
    return folders + files


def listing(root: str, path: str | None, label: str = "Drive") -> dict[str, Any]:
    _require_ready()
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
    _require_ready()
    key = _key(root, relative_path)
    if not key:
        return False
    try:
        if s3.exists(_bucket(), key, is_dir=False):
            return True
        return s3.exists(_bucket(), key, is_dir=True)
    except s3.S3Error as exc:
        raise DriveError(f"Gagal memeriksa folder. {exc}") from exc


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
    _require_ready()
    directory = normalize_dir(directory)
    name = clean_name(os.path.basename(filename))
    name = _unique_name(root, directory, name)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        s3.put_file(
            _bucket(),
            _key(root, _join(directory, name)),
            source,
            content_type=mime,
        )
    except s3.S3Error as exc:
        raise DriveError(f"Gagal mengunggah {name}. {exc}") from exc
    forget_usage(root)
    return name


def create_folder(root: str, directory: str, name: str) -> str:
    _require_ready()
    directory = normalize_dir(directory)
    name = clean_name(name)
    relative = _join(directory, name)
    if _exists(root, relative):
        raise DriveError(f"Folder “{name}” sudah ada.")
    # S3 tidak menyimpan folder kosong; penanda .keep membuat folder tetap tampil.
    try:
        s3.put_bytes(
            _bucket(),
            f"{_key(root, relative)}/{PLACEHOLDER}",
            b"",
            content_type="application/x-empty",
        )
    except s3.S3Error as exc:
        raise DriveError(f"Gagal membuat folder {name}. {exc}") from exc
    forget_usage(root)
    return relative


def delete_entry(root: str, path: str, is_dir: bool) -> str:
    _require_ready()
    relative = validate_path(path)
    if not relative:
        raise DriveError("Folder akar Drive tidak dapat dihapus.")
    key = _key(root, relative)
    try:
        if is_dir:
            s3.delete_prefix(_bucket(), f"{key}/")
        else:
            s3.delete_object(_bucket(), key)
    except s3.S3Error as exc:
        raise DriveError(
            f"Gagal menghapus {relative.rsplit('/', 1)[-1]}. {exc}"
        ) from exc
    forget_usage(root)
    return relative


def rename_entry(root: str, path: str, new_name: str, is_dir: bool) -> str:
    _require_ready()
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
    source_key = _key(root, relative)
    destination_key = _key(root, destination)
    try:
        if is_dir:
            s3.copy_prefix(_bucket(), f"{source_key}/", f"{destination_key}/")
            s3.delete_prefix(_bucket(), f"{source_key}/")
        else:
            s3.copy_object(_bucket(), source_key, destination_key)
            s3.delete_object(_bucket(), source_key)
    except s3.S3Error as exc:
        raise DriveError(f"Gagal mengubah nama {current}. {exc}") from exc
    forget_usage(root)
    return destination


def presigned_url(root: str, path: str, expire: int = LINK_TTL) -> str:
    """Tautan unduh langsung (presigned URL) agar browser mengambil dari HF S3.

    Server hanya menandatangani URL; byte berkas tidak melewati aplikasi.
    """
    _require_ready()
    relative = validate_path(path)
    if not relative:
        raise DriveError("Berkas tidak ditemukan.")
    try:
        return s3.presign(_bucket(), _key(root, relative), expire)
    except s3.S3Error as exc:
        raise DriveError(f"Gagal membuat tautan unduh langsung. {exc}") from exc


def download_file(root: str, path: str) -> tuple[str, str, str]:
    """Unduh berkas ke berkas sementara; kembalikan (path, nama, mime)."""
    _require_ready()
    relative = validate_path(path)
    if not relative:
        raise DriveError("Berkas tidak ditemukan.")
    name = relative.rsplit("/", 1)[-1]
    handle, temporary = tempfile.mkstemp(prefix="sidewa-drive-", suffix=".part")
    os.close(handle)
    try:
        s3.download_file(_bucket(), _key(root, relative), temporary)
    except s3.S3Error as exc:
        Path(temporary).unlink(missing_ok=True)
        raise DriveError(f"Gagal mengunduh {name}. {exc}") from exc
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    # Jangan pernah biarkan browser merender HTML/SVG dari Drive.
    if mime in {"text/html", "image/svg+xml", "application/xhtml+xml"}:
        mime = "application/octet-stream"
    return temporary, name, mime


def search(root: str, query: str) -> dict[str, Any]:
    _require_ready()
    term = (query or "").strip()
    if not term:
        return {"query": "", "results": [], "truncated": False}
    lowered = term.casefold()
    prefix = _folder_prefix(root, "")
    results: list[dict[str, Any]] = []
    truncated = False
    try:
        for obj in s3.iter_objects(_bucket(), prefix):
            key = str(obj.get("Key") or "")
            if not key.startswith(prefix):
                continue
            try:
                relative = validate_path(key[len(prefix) :])
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
                    "is_image": is_previewable(name),
                    "size": int(obj.get("Size") or 0),
                    "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
                }
            )
    except s3.S3Error as exc:
        raise DriveError(f"Gagal mencari berkas. {exc}") from exc
    return {"query": term, "results": results, "truncated": truncated}
