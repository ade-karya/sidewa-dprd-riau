"""Dashboard utama."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..audit import recent_audit
from ..constants import ROLE_ANGGOTA, ROLE_STAF_HUMAS
from ..database import get_db
from ..deps import require_user
from ..models import HumasStaffAccount, MemberAccount, User
from ..services import face_engine
from ..services.analytics import dashboard_stats
from ..templating import render

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if user.role == ROLE_ANGGOTA:
        account = db.query(MemberAccount).filter(MemberAccount.user_id == user.id).first()
        if account:
            return RedirectResponse(f"/dashboard-anggota/{account.member_id}", status_code=303)
    if user.role == ROLE_STAF_HUMAS:
        account = (
            db.query(HumasStaffAccount)
            .filter(HumasStaffAccount.user_id == user.id)
            .first()
        )
        if account:
            return RedirectResponse(f"/dashboard-staf/{account.staff_id}", status_code=303)
    stats = dashboard_stats(db, user)
    audits = recent_audit(db, 6) if user.role in {"superadmin", "admin"} else []
    return render(
        request,
        "dashboard.html",
        user=user,
        stats=stats,
        audits=audits,
        face_available=face_engine.engine.available,
    )
