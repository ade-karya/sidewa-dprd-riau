"""Penyajian media privat dengan pemeriksaan hak akses."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import CONTENT_MANAGER_ROLES, STATUS_PUBLISHED
from ..database import get_db
from ..deps import require_user
from ..models import ActivityPhoto, Member, MemberFace, MemberFaceLogin, User
from ..services.images import absolute_path

router = APIRouter()

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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

    photo = (
        db.query(ActivityPhoto)
        .filter((ActivityPhoto.file_path == path) | (ActivityPhoto.thumb_path == path))
        .first()
    )
    if photo:
        if not photo.activity:
            raise HTTPException(status_code=404, detail="Media tidak ditemukan.")
        if photo.activity.status != STATUS_PUBLISHED and user.role not in CONTENT_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Anda tidak dapat mengakses media draf.")
    else:
        member_media = (
            db.query(MemberFace).filter(MemberFace.image_path == path).first()
            or db.query(MemberFaceLogin).filter(MemberFaceLogin.image_path == path).first()
            or db.query(Member).filter(Member.portrait_path == path).first()
        )
        if not member_media:
            raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    if not file_path.is_file():
        from ..services import media_sync

        if not (
            settings.media_cache_on_demand and media_sync.download_to_cache(path)
        ):
            raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if media_type not in IMAGE_TYPES:
        raise HTTPException(status_code=404, detail="Media tidak ditemukan.")

    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
    return FileResponse(file_path, media_type=media_type, headers=headers)
