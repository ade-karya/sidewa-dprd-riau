"""Penyimpanan media lokal dan normalisasi gambar unggahan."""

from __future__ import annotations

import io
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import settings

logger = logging.getLogger("sidewa.images")

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ImageValidationError(ValueError):
    pass


@dataclass
class NormalizedImage:
    data: bytes
    thumbnail: bytes
    width: int
    height: int


def _clean_image(
    img: Image.Image, max_dimension: int, thumb_dimension: int = 760
) -> tuple[bytes, bytes, int, int]:
    try:
        img.seek(0)
    except Exception:
        pass
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    width, height = img.size

    clean = Image.new("RGB", (width, height))
    clean.paste(img)

    main_buf = io.BytesIO()
    clean.save(main_buf, format="JPEG", quality=88, optimize=True, progressive=True)

    thumb = clean.copy()
    thumb.thumbnail((thumb_dimension, thumb_dimension), Image.Resampling.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=82, optimize=True, progressive=True)

    return main_buf.getvalue(), thumb_buf.getvalue(), width, height


def normalize_upload(
    raw: bytes, *, max_dimension: int = 2560, thumb_dimension: int = 760
) -> NormalizedImage:
    if not raw:
        raise ImageValidationError("Berkas gambar kosong.")
    if len(raw) > settings.max_upload_bytes:
        raise ImageValidationError(f"Ukuran gambar melebihi batas {settings.max_upload_mb} MB.")
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("Berkas bukan gambar yang valid (JPG, PNG, atau WEBP).") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        if getattr(img, "is_animated", False):
            img.seek(0)
        width, height = img.size
        if width < 80 or height < 80:
            raise ImageValidationError("Resolusi gambar terlalu kecil (minimal 80×80 piksel).")
        if width * height > settings.max_image_pixels:
            raise ImageValidationError(
                f"Resolusi gambar terlalu besar (maksimal {settings.max_image_pixels // 1_000_000} megapiksel)."
            )
        if img.format not in ALLOWED_FORMATS:
            raise ImageValidationError("Format gambar harus JPG, PNG, atau WEBP.")
        img.load()
        data, thumb, w, h = _clean_image(img, max_dimension, thumb_dimension)
        return NormalizedImage(data=data, thumbnail=thumb, width=w, height=h)
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("Gambar tidak dapat diproses. Coba berkas lain.") from exc


def _kind_dir(kind: str) -> Path:
    if kind not in {"activities", "members", "staff"}:
        raise ValueError("Jenis media tidak dikenal")
    directory = settings.media_root / kind / datetime.now().strftime("%Y/%m")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_image(
    raw: bytes, kind: str, *, max_dimension: int = 2560, thumb_dimension: int = 760
) -> tuple[str, str, int, int]:
    """Simpan gambar + thumbnail. Mengembalikan path relatif."""
    normalized = normalize_upload(
        raw, max_dimension=max_dimension, thumb_dimension=thumb_dimension
    )
    directory = _kind_dir(kind)
    stem = uuid4().hex
    main_name = f"{stem}_{secrets.token_hex(2)}.jpg"
    thumb_name = f"{stem}_{secrets.token_hex(2)}_thumb.jpg"
    (directory / main_name).write_bytes(normalized.data)
    (directory / thumb_name).write_bytes(normalized.thumbnail)
    rel_main = (directory / main_name).relative_to(settings.media_root).as_posix()
    rel_thumb = (directory / thumb_name).relative_to(settings.media_root).as_posix()
    try:
        from . import media_sync

        media_sync.enqueue_upload(rel_main)
        media_sync.enqueue_upload(rel_thumb)
    except Exception:
        logger.exception("Gagal memasukkan media baru ke antrean HF S3")
    return rel_main, rel_thumb, normalized.width, normalized.height


def absolute_path(relative_path: str) -> Path:
    root = settings.media_root.resolve()
    candidate = (root / relative_path).resolve()
    if not str(candidate).startswith(str(root) + "/") and candidate != root:
        raise ValueError("Path media tidak valid")
    return candidate


def delete_paths(*relative_paths: str | None) -> None:
    for rel in relative_paths:
        if not rel:
            continue
        try:
            absolute_path(rel).unlink(missing_ok=True)
        except (ValueError, OSError):
            continue
        try:
            from . import media_sync

            media_sync.enqueue_delete(rel)
        except Exception:
            logger.exception("Gagal memasukkan media ke antrean hapus HF S3: %s", rel)


def copy_seed_image(source: Path, kind: str) -> tuple[str, str, int, int]:
    if kind == "activities":
        max_dimension, thumb_dimension = 2000, 760
    elif kind == "staff":
        # Foto staf Humas ditampilkan cukup besar pada kartu direktori dan
        # ruang kerja, jadi simpan thumbnail resolusi tinggi (hingga 1200 px).
        max_dimension, thumb_dimension = 2000, 1200
    else:
        max_dimension, thumb_dimension = 1200, 760
    return save_image(
        source.read_bytes(),
        kind,
        max_dimension=max_dimension,
        thumb_dimension=thumb_dimension,
    )


def media_size_bytes() -> int:
    if not settings.media_root.exists():
        return 0
    total = 0
    for path in settings.media_root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def ensure_media_tree() -> None:
    settings.ensure_dirs()


def cached_thumb(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    candidate = absolute_path(relative_path)
    if not candidate.exists():
        # Cache lokal bersifat sementara. Jika media sync + on-demand aktif,
        # tetap kembalikan path agar browser meminta dan router mengunduhnya.
        if settings.media_sync_enabled and settings.media_cache_on_demand:
            return relative_path
        return None
    return relative_path
