"""Pencarian dokumentasi berdasarkan wajah, nama, jabatan, dan lokasi."""

from __future__ import annotations

import base64
import os
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import CATEGORIES
from ..database import get_db
from ..deps import csrf_protect, flash, require_user
from ..models import Activity, Commission, Member, User
from ..services import face_engine
from ..services.images import ImageValidationError, normalize_upload
from ..services.search import (
    FaceSearchResult,
    Page,
    apply_filters,
    paginate,
    search_by_face,
    visible_query,
)
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])


def _all_commissions(db: Session) -> list[Commission]:
    return (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order, Commission.code)
        .all()
    )


def _member_matches(db: Session, q: str) -> list[Member]:
    if not q:
        return []
    like = f"%{q.strip()}%"
    return (
        db.query(Member)
        .filter(
            Member.is_active.is_(True),
            (Member.full_name.ilike(like))
            | (Member.position.ilike(like))
            | (Member.party.ilike(like))
            | (Member.dapil.ilike(like)),
        )
        .order_by(Member.full_name)
        .limit(6)
        .all()
    )


def _render_search(
    request: Request,
    db: Session,
    user: User,
    *,
    q: str = "",
    commission: str = "",
    category: str = "",
    location: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    face_result: FaceSearchResult | None = None,
    query_preview: str | None = None,
    error: str | None = None,
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
        )
    except ValueError:
        flash(request, "Format tanggal tidak valid.", "warning")

    activity_scores: dict[int, dict] = {}
    matched_members: list[dict] = []
    if face_result and face_result.matches:
        member_ids = [match["member"].id for match in face_result.matches]
        query = apply_filters(query, face_member_ids=member_ids)
        matched_members = face_result.matches
        score_by_member = {match["member"].id: match for match in face_result.matches}
        # Skor kegiatan dihitung setelah halaman diambil.
        result = paginate(
            query.order_by(Activity.activity_date.desc(), Activity.id.desc()), page, 9
        )
        for activity in result.items:
            best = None
            for member in activity.members:
                match = score_by_member.get(member.id)
                if match and (best is None or match["confidence"] > best["confidence"]):
                    best = {
                        "member": member,
                        "confidence": match["confidence"],
                        "distance": match["distance"],
                    }
            if best:
                activity_scores[activity.id] = best
    elif face_result:
        result = Page(items=[], total=0, page=1, per_page=9)
    else:
        result = paginate(
            query.order_by(Activity.activity_date.desc(), Activity.id.desc()), page, 9
        )

    return render(
        request,
        "search.html",
        user=user,
        result=result,
        commissions=_all_commissions(db),
        q=q,
        commission=commission,
        category=category,
        location=location,
        date_from=date_from,
        date_to=date_to,
        categories=CATEGORIES,
        face_result=face_result,
        matched_members=matched_members if face_result else _member_matches(db, q),
        activity_scores=activity_scores,
        query_preview=query_preview,
        error=error,
        face_available=face_engine.engine.available,
        mode="face" if face_result else "text",
    )


@router.get("/cari")
def search_page(
    request: Request,
    q: str = "",
    commission: str = "",
    category: str = "",
    location: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _render_search(
        request,
        db,
        user,
        q=q,
        commission=commission,
        category=category,
        location=location,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )


@router.post("/cari/wajah")
async def search_face(
    request: Request,
    photo: UploadFile = File(...),
    commission: str = Form(""),
    category: str = Form(""),
    location: str = Form(""),
    date_from: str = Form(""),
    date_to: str = Form(""),
    tolerance: float = Form(0.60),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not photo or not photo.filename:
        flash(request, "Pilih foto untuk mencari.", "warning")
        return _render_search(request, db, user, error="Pilih foto untuk mencari.")
    raw = await photo.read(25 * 1024 * 1024 + 1)
    try:
        normalized = normalize_upload(raw, max_dimension=1600)
    except ImageValidationError as exc:
        return _render_search(
            request,
            db,
            user,
            commission=commission,
            category=category,
            location=location,
            date_from=date_from,
            date_to=date_to,
            error=str(exc),
        )

    tolerance = min(0.70, max(0.35, float(tolerance or 0.60)))
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp:
            temp.write(normalized.data)
            temp_path = Path(temp.name)
        result = search_by_face(db, temp_path, tolerance=tolerance)
    finally:
        if temp_path and temp_path.exists():
            os.unlink(temp_path)

    preview = base64.b64encode(normalized.thumbnail).decode("ascii")
    if result.error and not result.matches:
        return _render_search(
            request,
            db,
            user,
            commission=commission,
            category=category,
            location=location,
            date_from=date_from,
            date_to=date_to,
            face_result=result,
            query_preview=preview,
            error=result.error,
        )

    audit(
        db,
        request,
        "SEARCH_FACE",
        actor=user,
        entity_type="search",
        summary=(
            f"Pencarian wajah: {result.query_faces} wajah terdeteksi, "
            f"{len(result.matches)} anggota cocok"
        ),
        detail={"faces": result.query_faces, "matches": len(result.matches)},
    )
    db.commit()
    return _render_search(
        request,
        db,
        user,
        commission=commission,
        category=category,
        location=location,
        date_from=date_from,
        date_to=date_to,
        face_result=result,
        query_preview=preview,
    )
