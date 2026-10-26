"""Pencatatan audit."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog, User


def audit(
    db: Session,
    request: Request | None,
    action: str,
    *,
    actor: User | None = None,
    entity_type: str = "",
    entity_id: int | None = None,
    summary: str = "",
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    ip = None
    user_agent = None
    if request is not None:
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = (
            forwarded.split(",")[0].strip()[:64]
            if forwarded
            else (request.client.host if request.client else None)
        )
        user_agent = (request.headers.get("user-agent") or "")[:300]
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "Sistem",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:400],
        detail=detail,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(entry)
    return entry


def recent_audit(db: Session, limit: int = 8) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
