"""Dashboard pribadi, direktori, dan Face ID staf Humas Sekretariat DPRD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import (
    ADMIN_ROLES,
    ROLE_STAF_HUMAS,
    STAFF_VIEW_ROLES,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles
from ..models import (
    HumasStaff,
    HumasStaffAccount,
    HumasStaffFaceLogin,
    User,
)
from ..services import face_engine
from ..services.humas_analytics import staff_dashboard_data, staff_overview
from ..services.images import (
    ImageValidationError,
    delete_paths,
    save_image,
)
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

STAFF_ACCESS = require_roles(*STAFF_VIEW_ROLES)
ADMIN = require_roles(*ADMIN_ROLES)


def _staff_or_404(db: Session, staff_id: int) -> HumasStaff:
    staff = db.get(HumasStaff, staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staf Humas tidak ditemukan.")
    return staff


def _account_for_user(db: Session, user: User) -> HumasStaffAccount | None:
    return (
        db.query(HumasStaffAccount)
        .filter(HumasStaffAccount.user_id == user.id)
        .first()
    )


def _ensure_can_view(db: Session, user: User, staff: HumasStaff) -> None:
    if user.role == ROLE_STAF_HUMAS:
        account = _account_for_user(db, user)
        if not account or account.staff_id != staff.id:
            raise HTTPException(
                status_code=403,
                detail="Anda hanya dapat membuka ruang kerja staf Humas milik sendiri.",
            )
        return
    if user.role not in STAFF_VIEW_ROLES:
        raise HTTPException(status_code=403, detail="Akses ditolak.")


@router.get("/staf-humas")
def staff_directory(
    request: Request,
    q: str = "",
    status: str = "active",
    user: User = Depends(STAFF_ACCESS),
    db: Session = Depends(get_db),
):
    query = db.query(HumasStaff)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                HumasStaff.full_name.ilike(like),
                HumasStaff.position.ilike(like),
                HumasStaff.unit.ilike(like),
            )
        )
    if status == "active":
        query = query.filter(HumasStaff.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(HumasStaff.is_active.is_(False))
    staff_list = query.order_by(
        HumasStaff.sort_order, HumasStaff.full_name
    ).all()
    own_staff_id = None
    if user.role == ROLE_STAF_HUMAS:
        account = _account_for_user(db, user)
        own_staff_id = account.staff_id if account else None
    return render(
        request,
        "humas/list.html",
        user=user,
        rows=staff_overview(db, staff_list),
        q=q,
        status=status,
        own_staff_id=own_staff_id,
        total_active=db.query(HumasStaff).filter(HumasStaff.is_active.is_(True)).count(),
        total_faces=db.query(HumasStaffFaceLogin)
        .filter(HumasStaffFaceLogin.is_active.is_(True))
        .count(),
    )


@router.get("/dashboard-staf")
def my_staff_dashboard(
    request: Request,
    user: User = Depends(STAFF_ACCESS),
    db: Session = Depends(get_db),
):
    if user.role == ROLE_STAF_HUMAS:
        account = _account_for_user(db, user)
        if not account:
            raise HTTPException(
                status_code=403,
                detail="Akun ini belum terhubung dengan data staf Humas.",
            )
        return RedirectResponse(f"/dashboard-staf/{account.staff_id}", status_code=303)
    return RedirectResponse("/staf-humas", status_code=303)


@router.get("/dashboard-staf/{staff_id}")
def staff_dashboard(
    staff_id: int,
    request: Request,
    user: User = Depends(STAFF_ACCESS),
    db: Session = Depends(get_db),
):
    staff = _staff_or_404(db, staff_id)
    _ensure_can_view(db, user, staff)
    data = staff_dashboard_data(db, staff, user)
    return render(
        request,
        "humas/dashboard.html",
        user=user,
        staff=staff,
        data=data,
        face_available=face_engine.engine.available,
    )


@router.post("/staf-humas/{staff_id}/foto")
async def upload_staff_portrait(
    staff_id: int,
    request: Request,
    portrait: UploadFile = File(...),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    staff = _staff_or_404(db, staff_id)
    if not portrait or not portrait.filename:
        flash(request, "Pilih berkas foto terlebih dahulu.", "danger")
        return RedirectResponse(f"/dashboard-staf/{staff.id}", status_code=303)
    raw = await portrait.read(settings.max_upload_bytes + 1)
    try:
        rel_main, rel_thumb, _, _ = save_image(raw, "staff", max_dimension=1600)
    except ImageValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/dashboard-staf/{staff.id}", status_code=303)
    old = staff.portrait_path
    staff.portrait_path = rel_thumb
    audit(
        db,
        request,
        "STAFF_PORTRAIT_UPDATE",
        actor=user,
        entity_type="staff",
        entity_id=staff.id,
        summary=f"Memperbarui foto staf Humas {staff.full_name}",
    )
    db.commit()
    delete_paths(old, rel_main)
    flash(request, f"Foto {staff.full_name} berhasil diperbarui.", "success")
    return RedirectResponse(f"/dashboard-staf/{staff.id}", status_code=303)


@router.post("/staf-humas/{staff_id}/face-login/hapus")
def delete_staff_face_login(
    staff_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    staff = _staff_or_404(db, staff_id)
    rows = (
        db.query(HumasStaffFaceLogin)
        .filter(HumasStaffFaceLogin.staff_id == staff.id)
        .all()
    )
    if not rows:
        flash(request, "Staf ini belum memiliki Face ID.", "warning")
        return RedirectResponse(f"/dashboard-staf/{staff.id}", status_code=303)
    paths = [row.image_path for row in rows]
    for row in rows:
        db.delete(row)
    audit(
        db,
        request,
        "FACE_LOGIN_DELETE",
        actor=user,
        entity_type="staff",
        entity_id=staff.id,
        summary=f"Menghapus Face ID login staf Humas {staff.full_name}",
    )
    db.commit()
    for path in paths:
        delete_paths(path)
    flash(
        request,
        "Face ID staf dihapus. Staf dapat mendaftarkan ulang wajah pada halaman login.",
        "success",
    )
    return RedirectResponse(f"/dashboard-staf/{staff.id}", status_code=303)
