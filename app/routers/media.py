"""Penyajian media privat dengan pemeriksaan hak akses."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import BASE_DIR, settings
from ..constants import ADMIN_ROLES, CONTENT_MANAGER_ROLES, STATUS_PUBLISHED
from ..database import get_db
from ..deps import require_user
from ..models import (
    ActivityPhoto,
    HumasStaff,
    Member,
    MemberFace,
    MemberFaceLogin,
    PhotoSelectionItem,
    User,
)
from ..services.images import absolute_path, path_variants

router = APIRouter()

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
STAFF_PORTRAIT_DIR = BASE_DIR / "seed_assets" / "staff_portraits"


def _bundled_staff_portrait(staff: HumasStaff) -> Path | None:
    """Foto staf bawaan repo, dipakai bila cache lokal & HF S3 tidak tersedia."""
    if not STAFF_PORTRAIT_DIR.is_dir():
        return None
    names = [f"{staff.sort_order:02d}", str(staff.sort_order)]
    slug = re.sub(r"[^a-z0-9]+", "-", (staff.full_name or "").lower()).strip("-")
    if slug:
        names.append(slug)
    for name in names:
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = STAFF_PORTRAIT_DIR / f"{name}{suffix}"
            if candidate.is_file():
                return candidate
    return None


@router.get("/media/{path:path}")
def serve_media(
    path: str,
    request: Request,
    download: bool = False,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        file_path = absolute_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.") from exc

    variants = path_variants(path)

    photo = (
        db.query(ActivityPhoto)
        .filter(
            (ActivityPhoto.file_path.in_(variants))
            | (ActivityPhoto.thumb_path.in_(variants))
        )
        .first()
    )
    member_media = None
    if photo:
        if not photo.activity:
            raise HTTPException(status_code=404, detail="Media tidak ditemukan.")
        if photo.activity.status != STATUS_PUBLISHED and user.role not in CONTENT_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Anda tidak dapat mengakses media draf.")
    else:
        selection_item = (
            db.query(PhotoSelectionItem)
            .filter(
                (PhotoSelectionItem.file_path.in_(variants))
                | (PhotoSelectionItem.thumb_path.in_(variants))
            )
            .first()
        )
        if selection_item:
            run = selection_item.run
            if not run or (
                run.user_id != user.id and user.role not in ADMIN_ROLES
            ):
                raise HTTPException(
                    status_code=403, detail="Media seleksi foto ini bukan milik Anda."
                )
        else:
            member_media = (
                db.query(MemberFace)
                .filter(MemberFace.image_path.in_(variants))
                .first()
                or db.query(MemberFaceLogin)
                .filter(MemberFaceLogin.image_path.in_(variants))
                .first()
                or db.query(Member)
                .filter(Member.portrait_path.in_(variants))
                .first()
                or db.query(HumasStaff)
                .filter(HumasStaff.portrait_path.in_(variants))
                .first()
            )
            if not member_media:
                raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    if not file_path.is_file():
        # Path utama/thumbnail bisa saja belum ada di cache lokal; coba
        # pasangannya sebelum meminta unduhan on-demand.
        for variant in variants:
            try:
                candidate = absolute_path(variant)
            except ValueError:
                continue
            if candidate.is_file():
                file_path = candidate
                break
        else:
            from ..services import media_sync

            if settings.media_cache_on_demand:
                for variant in variants:
                    if media_sync.download_to_cache(variant):
                        file_path = absolute_path(variant)
                        break
            if not file_path.is_file() and isinstance(member_media, HumasStaff):
                # HF S3 bisa saja tidak tersedia (mis. server baru tanpa cache).
                # Foto resmi staf Humas tetap tampil dari aset bawaan.
                fallback = _bundled_staff_portrait(member_media)
                if fallback and fallback.is_file():
                    file_path = fallback
            if not file_path.is_file():
                raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if media_type not in IMAGE_TYPES:
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
    return FileResponse(file_path, media_type=media_type, headers=headers)
