"""Jejak audit aktivitas pengguna."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import ADMIN_ROLES, AUDIT_ACTIONS
from ..database import get_db
from ..deps import csrf_protect, require_roles
from ..models import AuditLog, User
from ..services.search import Page, paginate
from ..templating import render
from ..utils import local_now

router = APIRouter(dependencies=[Depends(csrf_protect)])

ADMIN = require_roles(*ADMIN_ROLES)


@router.get("/audit")
def audit_list(
    request: Request,
    q: str = "",
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                AuditLog.actor_name.ilike(like),
                AuditLog.summary.ilike(like),
                AuditLog.entity_type.ilike(like),
            )
        )
    if action in AUDIT_ACTIONS:
        query = query.filter(AuditLog.action == action)
    try:
        if date_from:
            query = query.filter(AuditLog.created_at >= date.fromisoformat(date_from))
        if date_to:
            query = query.filter(AuditLog.created_at < date.fromisoformat(date_to))
    except ValueError:
        pass
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    result: Page = paginate(query, page, 30)
    return render(
        request,
        "audit/list.html",
        user=user,
        result=result,
        q=q,
        action=action,
        date_from=date_from,
        date_to=date_to,
        actions=AUDIT_ACTIONS,
        total=db.query(AuditLog).count(),
    )


@router.get("/audit/ekspor.csv")
def export_audit(
    request: Request,
    q: str = "",
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                AuditLog.actor_name.ilike(like),
                AuditLog.summary.ilike(like),
                AuditLog.entity_type.ilike(like),
            )
        )
    if action in AUDIT_ACTIONS:
        query = query.filter(AuditLog.action == action)
    try:
        if date_from:
            query = query.filter(AuditLog.created_at >= date.fromisoformat(date_from))
        if date_to:
            query = query.filter(AuditLog.created_at < date.fromisoformat(date_to))
    except ValueError:
        pass
    rows = query.order_by(AuditLog.created_at.desc()).limit(10000).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Waktu", "Aktor", "Aksi", "Entitas", "ID", "Ringkasan", "IP"])
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(timespec="seconds"),
                row.actor_name,
                AUDIT_ACTIONS.get(row.action, row.action),
                row.entity_type,
                row.entity_id or "",
                row.summary,
                row.ip_address or "",
            ]
        )
    audit(
        db,
        request,
        "ACTIVITY_UPDATE",
        actor=user,
        entity_type="audit",
        summary="Mengekspor log audit ke CSV",
    )
    db.commit()
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="audit-sidewa-{local_now():%Y%m%d}.csv"'
        },
    )
