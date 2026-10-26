"""Halaman komisi DPRD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import ADMIN_ROLES
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles, require_user
from ..models import Activity, Commission, Member, User
from ..services.search import visible_query
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

ADMIN = require_roles(*ADMIN_ROLES)


def _commissions(db: Session) -> list[Commission]:
    return (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order, Commission.code)
        .all()
    )


def _or_404(db: Session, commission_id: int) -> Commission:
    commission = db.get(Commission, commission_id)
    if not commission:
        raise HTTPException(status_code=404, detail="Komisi tidak ditemukan.")
    return commission


@router.get("/komisi")
def list_commissions(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    stats = []
    base = visible_query(db, user)
    for commission in _commissions(db):
        stats.append(
            {
                "commission": commission,
                "members": db.query(Member)
                .filter(Member.commission_id == commission.id, Member.is_active.is_(True))
                .count(),
                "activities": base.filter(
                    Activity.commissions.any(Commission.id == commission.id)
                ).count(),
                "staff": db.query(User)
                .filter(User.commission_id == commission.id, User.is_active.is_(True))
                .count(),
            }
        )
    return render(request, "commissions/list.html", user=user, stats=stats)


@router.get("/komisi/{commission_id}")
def commission_detail(
    commission_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    commission = _or_404(db, commission_id)
    members = (
        db.query(Member)
        .filter(Member.commission_id == commission.id, Member.is_active.is_(True))
        .order_by(Member.full_name)
        .all()
    )
    activities = (
        visible_query(db, user)
        .filter(Activity.commissions.any(Commission.id == commission.id))
        .order_by(Activity.activity_date.desc())
        .limit(12)
        .all()
    )
    staff = (
        db.query(User)
        .filter(User.commission_id == commission.id, User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    return render(
        request,
        "commissions/detail.html",
        user=user,
        commission=commission,
        members=members,
        activities=activities,
        staff=staff,
    )


@router.post("/komisi/{commission_id}/edit")
def update_commission(
    commission_id: int,
    request: Request,
    name: str = Form(...),
    bidang: str = Form(""),
    description: str = Form(""),
    color: str = Form("#7E4890"),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    commission = _or_404(db, commission_id)
    if len(name.strip()) < 3:
        flash(request, "Nama komisi minimal 3 karakter.", "danger")
        return RedirectResponse(f"/komisi/{commission.id}", status_code=303)
    if not color.startswith("#") or len(color) not in {4, 7}:
        color = commission.color
    commission.name = name.strip()[:80]
    commission.bidang = bidang.strip()[:255]
    commission.description = description.strip()
    commission.color = color
    audit(
        db,
        request,
        "COMMISSION_UPDATE",
        actor=user,
        entity_type="commission",
        entity_id=commission.id,
        summary=f"Memperbarui profil {commission.name}",
    )
    db.commit()
    flash(request, "Profil komisi diperbarui.", "success")
    return RedirectResponse(f"/komisi/{commission.id}", status_code=303)
