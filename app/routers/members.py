"""Direktori anggota DPRD dan pendaftaran data wajah."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import ADMIN_ROLES, CONTENT_MANAGER_ROLES
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles, require_user
from ..models import Activity, ActivityMember, Commission, Member, MemberFace, User, utcnow
from ..services import face_engine
from ..services.images import (
    ImageValidationError,
    absolute_path,
    delete_paths,
    save_image,
)
from ..services.search import Page, paginate, visible_query
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

ADMIN = require_roles(*ADMIN_ROLES)
MANAGER = require_roles(*CONTENT_MANAGER_ROLES)


def _commissions(db: Session) -> list[Commission]:
    return (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order, Commission.code)
        .all()
    )


def _member_or_404(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan.")
    return member


def _commission_by_code(db: Session, code: str) -> Commission | None:
    if not code:
        return None
    return db.query(Commission).filter(Commission.code == code).first()


def _form_values(member: Member | None = None) -> dict:
    if not member:
        return {
            "full_name": "",
            "position": "",
            "commission_code": "",
            "party": "",
            "dapil": "",
            "email": "",
            "phone": "",
            "bio": "",
        }
    return {
        "full_name": member.full_name,
        "position": member.position,
        "commission_code": member.commission.code if member.commission else "",
        "party": member.party,
        "dapil": member.dapil,
        "email": member.email or "",
        "phone": member.phone or "",
        "bio": member.bio,
    }


def _enroll_from_path(
    db: Session,
    member: Member,
    image_path: str,
    *,
    created_by: User,
    source: str = "upload",
) -> tuple[MemberFace | None, str | None]:
    try:
        detected = face_engine.engine.detect_single(absolute_path(image_path))
    except face_engine.FaceEngineError as exc:
        return None, str(exc)
    has_primary = any(face.is_primary for face in member.faces)
    face = MemberFace(
        member_id=member.id,
        image_path=image_path,
        encoding=detected.encoding,
        quality=detected.quality,
        is_primary=not has_primary,
        source=source,
        created_by_id=created_by.id,
    )
    db.add(face)
    db.flush()
    return face, None


@router.get("/anggota")
def list_members(
    request: Request,
    q: str = "",
    commission: str = "",
    status: str = "active",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = db.query(Member)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Member.full_name.ilike(like),
                Member.position.ilike(like),
                Member.party.ilike(like),
                Member.dapil.ilike(like),
            )
        )
    if commission:
        query = query.join(Commission, Member.commission_id == Commission.id).filter(
            Commission.code == commission
        )
    if status == "active":
        query = query.filter(Member.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Member.is_active.is_(False))
    query = query.order_by(Member.commission_id.is_(None), Member.full_name)
    result: Page = paginate(query, page, 16)
    return render(
        request,
        "members/list.html",
        user=user,
        result=result,
        commissions=_commissions(db),
        q=q,
        commission=commission,
        status=status,
        total_active=db.query(Member).filter(Member.is_active.is_(True)).count(),
        total_faces=db.query(MemberFace).count(),
    )


@router.get("/anggota/baru")
def new_member(
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "members/form.html",
        user=user,
        member=None,
        form=_form_values(),
        commissions=_commissions(db),
        mode="create",
    )


@router.post("/anggota")
async def create_member(
    request: Request,
    full_name: str = Form(...),
    position: str = Form(...),
    commission_code: str = Form(""),
    party: str = Form(""),
    dapil: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    bio: str = Form(""),
    consent: bool = Form(False),
    portrait: UploadFile | None = File(None),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    form = {
        "full_name": full_name,
        "position": position,
        "commission_code": commission_code,
        "party": party,
        "dapil": dapil,
        "email": email,
        "phone": phone,
        "bio": bio,
    }
    if not consent:
        return render(
            request,
            "members/form.html",
            user=user,
            status_code=400,
            member=None,
            form=form,
            commissions=_commissions(db),
            mode="create",
            error="Persetujuan penggunaan data biometrik wajib dicentang.",
        )
    full_name = full_name.strip()
    position = position.strip()
    if len(full_name) < 3 or len(position) < 2:
        return render(
            request,
            "members/form.html",
            user=user,
            status_code=400,
            member=None,
            form=form,
            commissions=_commissions(db),
            mode="create",
            error="Nama lengkap dan jabatan wajib diisi dengan benar.",
        )
    commission = _commission_by_code(db, commission_code)
    member = Member(
        full_name=full_name[:160],
        position=position[:160],
        commission_id=commission.id if commission else None,
        party=party.strip()[:80],
        dapil=dapil.strip()[:120],
        email=email.strip() or None,
        phone=phone.strip() or None,
        bio=bio.strip(),
        is_active=True,
        consent_granted_at=utcnow(),
        consent_note="Persetujuan tercatat pada formulir pendaftaran anggota.",
    )
    db.add(member)
    db.flush()

    saved: list[str] = []
    warning = None
    if portrait and portrait.filename:
        try:
            raw = await portrait.read(15 * 1024 * 1024 + 1)
            rel_main, rel_thumb, _, _ = save_image(raw, "members", max_dimension=1400)
            saved.extend([rel_main, rel_thumb])
            member.portrait_path = rel_thumb
            _, warning = _enroll_from_path(db, member, rel_main, created_by=user)
        except ImageValidationError as exc:
            db.rollback()
            for path in saved:
                delete_paths(path)
            return render(
                request,
                "members/form.html",
                user=user,
                status_code=400,
                member=None,
                form=form,
                commissions=_commissions(db),
                mode="create",
                error=str(exc),
            )
    audit(
        db,
        request,
        "MEMBER_CREATE",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=f"Menambahkan anggota {member.full_name} — {member.position}",
    )
    db.commit()
    flash(request, f"Anggota {member.full_name} berhasil ditambahkan.", "success")
    if warning:
        flash(request, f"Potret tersimpan, tetapi wajah belum terdaftar: {warning}", "warning")
    return RedirectResponse(f"/anggota/{member.id}", status_code=303)


@router.get("/anggota/{member_id}")
def member_detail(
    member_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    activities = (
        visible_query(db, user)
        .filter(Activity.member_links.any(ActivityMember.member_id == member.id))
        .order_by(Activity.activity_date.desc())
        .limit(12)
        .all()
    )
    activity_count = (
        visible_query(db, user)
        .filter(Activity.member_links.any(ActivityMember.member_id == member.id))
        .count()
    )
    return render(
        request,
        "members/detail.html",
        user=user,
        member=member,
        activities=activities,
        activity_count=activity_count,
        face_available=face_engine.engine.available,
    )


@router.get("/anggota/{member_id}/edit")
def edit_member(
    member_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    return render(
        request,
        "members/form.html",
        user=user,
        member=member,
        form=_form_values(member),
        commissions=_commissions(db),
        mode="edit",
    )


@router.post("/anggota/{member_id}/edit")
async def update_member(
    member_id: int,
    request: Request,
    full_name: str = Form(...),
    position: str = Form(...),
    commission_code: str = Form(""),
    party: str = Form(""),
    dapil: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    bio: str = Form(""),
    portrait: UploadFile | None = File(None),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    form = {
        "full_name": full_name,
        "position": position,
        "commission_code": commission_code,
        "party": party,
        "dapil": dapil,
        "email": email,
        "phone": phone,
        "bio": bio,
    }
    if len(full_name.strip()) < 3 or len(position.strip()) < 2:
        return render(
            request,
            "members/form.html",
            user=user,
            status_code=400,
            member=member,
            form=form,
            commissions=_commissions(db),
            mode="edit",
            error="Nama lengkap dan jabatan wajib diisi dengan benar.",
        )
    commission = _commission_by_code(db, commission_code)
    member.full_name = full_name.strip()[:160]
    member.position = position.strip()[:160]
    member.commission_id = commission.id if commission else None
    member.party = party.strip()[:80]
    member.dapil = dapil.strip()[:120]
    member.email = email.strip() or None
    member.phone = phone.strip() or None
    member.bio = bio.strip()

    warning = None
    if portrait and portrait.filename:
        try:
            raw = await portrait.read(15 * 1024 * 1024 + 1)
            rel_main, rel_thumb, _, _ = save_image(raw, "members", max_dimension=1400)
            member.portrait_path = rel_thumb
            _, warning = _enroll_from_path(db, member, rel_main, created_by=user)
        except ImageValidationError as exc:
            flash(request, f"Potret baru gagal disimpan: {exc}", "warning")
    audit(
        db,
        request,
        "MEMBER_UPDATE",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=f"Memperbarui data anggota {member.full_name}",
    )
    db.commit()
    flash(request, "Data anggota berhasil diperbarui.", "success")
    if warning:
        flash(request, f"Potret tersimpan, tetapi wajah belum terdaftar: {warning}", "warning")
    return RedirectResponse(f"/anggota/{member.id}", status_code=303)


@router.post("/anggota/{member_id}/status")
def toggle_member(
    member_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    member.is_active = not member.is_active
    audit(
        db,
        request,
        "MEMBER_DEACTIVATE",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=(
            f"Mengaktifkan anggota {member.full_name}"
            if member.is_active
            else f"Menonaktifkan anggota {member.full_name}"
        ),
    )
    db.commit()
    flash(
        request,
        f"Anggota {'diaktifkan' if member.is_active else 'dinonaktifkan'}.",
        "success",
    )
    return RedirectResponse(f"/anggota/{member.id}", status_code=303)


@router.post("/anggota/{member_id}/wajah")
async def enroll_face(
    member_id: int,
    request: Request,
    photo: UploadFile = File(...),
    consent: bool = Form(False),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    if not consent:
        flash(
            request,
            "Konfirmasi persetujuan anggota diperlukan sebelum mendaftarkan wajah.",
            "danger",
        )
        return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)
    if not photo or not photo.filename:
        flash(request, "Pilih foto wajah yang akan didaftarkan.", "warning")
        return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)
    raw = await photo.read(15 * 1024 * 1024 + 1)
    saved: list[str] = []
    try:
        rel_main, rel_thumb, _, _ = save_image(raw, "members", max_dimension=1400)
        saved.extend([rel_main, rel_thumb])
        face, error = _enroll_from_path(db, member, rel_main, created_by=user)
        if error:
            db.rollback()
            for path in saved:
                delete_paths(path)
            flash(request, error, "danger")
            return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)
        if not member.portrait_path:
            member.portrait_path = rel_thumb
        audit(
            db,
            request,
            "FACE_ENROLL",
            actor=user,
            entity_type="member",
            entity_id=member.id,
            summary=f"Mendaftarkan data wajah baru untuk {member.full_name}",
            detail={"face_id": face.id, "quality": face.quality},
        )
        db.commit()
    except ImageValidationError as exc:
        db.rollback()
        for path in saved:
            delete_paths(path)
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)
    flash(request, f"Wajah berhasil didaftarkan untuk {member.full_name}.", "success")
    return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)


@router.post("/anggota/{member_id}/wajah/{face_id}/hapus")
def delete_face(
    member_id: int,
    face_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    face = (
        db.query(MemberFace)
        .filter(MemberFace.id == face_id, MemberFace.member_id == member.id)
        .first()
    )
    if not face:
        raise HTTPException(status_code=404, detail="Data wajah tidak ditemukan.")
    was_primary = face.is_primary
    delete_paths(face.image_path)
    db.delete(face)
    db.flush()
    if was_primary:
        remaining = (
            db.query(MemberFace)
            .filter(MemberFace.member_id == member.id, MemberFace.id != face.id)
            .order_by(MemberFace.id)
            .first()
        )
        if remaining:
            remaining.is_primary = True
    audit(
        db,
        request,
        "FACE_DELETE",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=f"Menghapus satu data wajah {member.full_name}",
    )
    db.commit()
    flash(request, "Data wajah dihapus dari sistem.", "success")
    return RedirectResponse(f"/anggota/{member.id}#wajah", status_code=303)
