"""REST API v1 untuk integrasi dan aplikasi eksternal."""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import CONTENT_MANAGER_ROLES, STATUS_PUBLISHED
from ..database import get_db
from ..deps import api_user
from ..models import Activity, ActivityMember, Commission, Member, User
from ..services.analytics import dashboard_stats
from ..services.images import ImageValidationError, normalize_upload
from ..services.search import (
    FaceSearchResult,
    apply_filters,
    paginate,
    search_by_face,
    visible_query,
)
from ..utils import to_local

router = APIRouter(prefix="/api/v1", tags=["SIDEWA API"])


def _iso(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    local = to_local(value)
    return local.isoformat() if local else None


def _media_url(request: Request, path: str | None) -> str | None:
    if not path:
        return None
    return str(request.base_url).rstrip("/") + "/media/" + path


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "commission": user.commission.code if user.commission else None,
        "is_active": user.is_active,
        "last_login_at": _iso(user.last_login_at),
    }


def _serialize_commission(commission: Commission) -> dict:
    return {
        "id": commission.id,
        "code": commission.code,
        "name": commission.name,
        "bidang": commission.bidang,
        "description": commission.description,
        "color": commission.color,
    }


def _serialize_member(member: Member, request: Request, db: Session) -> dict:
    activity_count = db.query(ActivityMember).filter(ActivityMember.member_id == member.id).count()
    return {
        "id": member.id,
        "full_name": member.full_name,
        "position": member.position,
        "commission": _serialize_commission(member.commission) if member.commission else None,
        "party": member.party,
        "dapil": member.dapil,
        "photo_url": _media_url(request, member.portrait_path),
        "is_active": member.is_active,
        "registered_faces": len(member.faces),
        "activity_count": activity_count,
    }


def _serialize_photo(photo, request: Request) -> dict:
    return {
        "id": photo.id,
        "url": _media_url(request, photo.file_path),
        "thumb_url": _media_url(request, photo.thumb_path),
        "width": photo.width,
        "height": photo.height,
        "caption": photo.caption,
        "status": photo.status,
        "face_count": photo.face_count,
    }


def _serialize_activity(
    activity: Activity, request: Request, db: Session, detail: bool = False
) -> dict:
    payload = {
        "id": activity.id,
        "code": activity.code,
        "title": activity.title,
        "category": activity.category,
        "status": activity.status,
        "activity_date": activity.activity_date.isoformat(),
        "start_time": activity.start_time,
        "end_time": activity.end_time,
        "location_name": activity.location_name,
        "location_address": activity.location_address,
        "latitude": activity.latitude,
        "longitude": activity.longitude,
        "commissions": [_serialize_commission(c) for c in activity.commissions],
        "cover_url": _media_url(request, activity.cover.thumb_path if activity.cover else None),
        "member_count": activity.confirmed_member_count,
        "published_at": _iso(activity.published_at),
        "view_count": activity.view_count,
    }
    if detail:
        payload.update(
            {
                "description": activity.description,
                "created_by": activity.creator.full_name if activity.creator else None,
                "created_at": _iso(activity.created_at),
                "updated_at": _iso(activity.updated_at),
                "photos": [_serialize_photo(photo, request) for photo in activity.photos],
                "members": [
                    _serialize_member(link.member, request, db) if link.member else None
                    for link in activity.member_links
                    if link.confirmed
                ],
                "face_tags": [
                    {
                        "photo_id": detection.photo_id,
                        "member_id": detection.member_id,
                        "member_name": detection.member.full_name if detection.member else None,
                        "confidence": detection.confidence,
                        "distance": detection.distance,
                        "confirmed": detection.is_confirmed,
                        "bbox": {
                            "top": detection.bbox_top,
                            "right": detection.bbox_right,
                            "bottom": detection.bbox_bottom,
                            "left": detection.bbox_left,
                        },
                    }
                    for detection in activity.detections
                    if detection.is_confirmed
                ],
            }
        )
    return payload


@router.get("/me", summary="Profil pengguna terautentikasi")
def me(user: User = Depends(api_user)):
    return {
        "data": _serialize_user(user),
        "permissions": {
            "manage_content": user.role in CONTENT_MANAGER_ROLES,
            "manage_users": user.role in {"superadmin", "admin"},
            "view_audit": user.role in {"superadmin", "admin"},
        },
    }


@router.get("/commissions", summary="Daftar komisi")
def api_commissions(user: User = Depends(api_user), db: Session = Depends(get_db)):
    items = db.query(Commission).order_by(Commission.sort_order).all()
    return {"data": [_serialize_commission(item) for item in items]}


@router.get("/members", summary="Cari anggota DPRD")
def api_members(
    request: Request,
    q: str = "",
    commission: str = "",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(api_user),
    db: Session = Depends(get_db),
):
    query = db.query(Member).filter(Member.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Member.full_name.ilike(like))
            | (Member.position.ilike(like))
            | (Member.party.ilike(like))
            | (Member.dapil.ilike(like))
        )
    if commission:
        query = query.join(Commission, Member.commission_id == Commission.id).filter(
            Commission.code == commission
        )
    total = query.count()
    items = query.order_by(Member.full_name).offset(offset).limit(limit).all()
    return {
        "data": [_serialize_member(item, request, db) for item in items],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/activities", summary="Daftar dokumentasi kegiatan")
def api_activities(
    request: Request,
    q: str = "",
    commission: str = "",
    category: str = "",
    location: str = "",
    date_from: str = "",
    date_to: str = "",
    member_id: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    user: User = Depends(api_user),
    db: Session = Depends(get_db),
):
    query = visible_query(db, user)
    try:
        query = apply_filters(
            query,
            q=q,
            commission=commission,
            category=category,
            location=location,
            date_from=date.fromisoformat(date_from) if date_from else None,
            date_to=date.fromisoformat(date_to) if date_to else None,
            member_id=member_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Format tanggal tidak valid.") from exc
    result = paginate(
        query.order_by(Activity.activity_date.desc(), Activity.id.desc()), page, per_page
    )
    return {
        "data": [_serialize_activity(item, request, db) for item in result.items],
        "meta": {
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        },
    }


@router.get("/activities/{activity_id}", summary="Detail kegiatan")
def api_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(api_user),
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Kegiatan tidak ditemukan.")
    if activity.status != STATUS_PUBLISHED and user.role not in CONTENT_MANAGER_ROLES:
        raise HTTPException(status_code=404, detail="Kegiatan tidak ditemukan.")
    return {"data": _serialize_activity(activity, request, db, detail=True)}


@router.post("/search/face", summary="Cari kegiatan berdasarkan wajah")
async def api_search_face(
    request: Request,
    photo: UploadFile = File(...),
    commission: str = Form(""),
    category: str = Form(""),
    location: str = Form(""),
    date_from: str = Form(""),
    date_to: str = Form(""),
    tolerance: float = Form(0.60),
    user: User = Depends(api_user),
    db: Session = Depends(get_db),
):
    raw = await photo.read(25 * 1024 * 1024 + 1)
    try:
        normalized = normalize_upload(raw, max_dimension=1600)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp:
            temp.write(normalized.data)
            temp_path = Path(temp.name)
        result: FaceSearchResult = search_by_face(
            db, temp_path, tolerance=min(0.70, max(0.35, tolerance or 0.60))
        )
    finally:
        if temp_path and temp_path.exists():
            os.unlink(temp_path)
    if result.error and not result.matches:
        raise HTTPException(status_code=422, detail=result.error)

    member_ids = [match["member"].id for match in result.matches]
    query = visible_query(db, user)
    try:
        query = apply_filters(
            query,
            commission=commission,
            category=category,
            location=location,
            date_from=date.fromisoformat(date_from) if date_from else None,
            date_to=date.fromisoformat(date_to) if date_to else None,
            face_member_ids=member_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Format tanggal tidak valid.") from exc
    activities = query.order_by(Activity.activity_date.desc()).limit(20).all() if member_ids else []
    audit(
        db,
        request,
        "SEARCH_FACE",
        actor=user,
        entity_type="search",
        summary=(
            f"API pencarian wajah: {result.query_faces} wajah, {len(result.matches)} anggota cocok"
        ),
    )
    db.commit()
    return {
        "data": {
            "query_faces": result.query_faces,
            "unknown_faces": result.unknown_faces,
            "matches": [
                {
                    "member": _serialize_member(match["member"], request, db),
                    "distance": match["distance"],
                    "confidence": match["confidence"],
                }
                for match in result.matches
            ],
            "activities": [_serialize_activity(item, request, db) for item in activities],
        }
    }


@router.get("/stats", summary="Statistik dokumentasi")
def api_stats(user: User = Depends(api_user), db: Session = Depends(get_db)):
    stats = dashboard_stats(db, user)
    return {
        "data": {
            "total_activities": stats["total_activities"],
            "published": stats["published"],
            "total_members": stats["total_members"],
            "total_photos": stats["total_photos"],
            "recognized_faces": stats["recognized_faces"],
            "storage_bytes": stats["storage_bytes"],
            "commissions": [
                {
                    "code": item["commission"].code,
                    "name": item["commission"].name,
                    "activities": item["activities"],
                    "members": item["members"],
                }
                for item in stats["commission_stats"]
            ],
            "categories": stats["category_stats"],
            "monthly": stats["monthly"],
        }
    }
