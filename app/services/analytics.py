"""Agregasi statistik dashboard."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..constants import STATUS_PUBLISHED
from ..models import (
    Activity,
    ActivityMember,
    ActivityPhoto,
    AuditLog,
    Commission,
    Member,
    User,
)
from ..utils import date_range_last_months, local_now, month_label, utc_naive_now
from .images import media_size_bytes
from .search import visible_query


def dashboard_stats(db: Session, user: User) -> dict:
    base = visible_query(db, user)
    total_activities = base.count()
    published = base.filter(Activity.status == STATUS_PUBLISHED).count()
    total_members = db.query(Member).filter(Member.is_active.is_(True)).count()
    total_photos = (
        db.query(ActivityPhoto)
        .join(Activity, ActivityPhoto.activity_id == Activity.id)
        .filter(Activity.status == STATUS_PUBLISHED)
        .count()
    )
    recognized = (
        db.query(func.count(ActivityMember.id))
        .join(Activity, ActivityMember.activity_id == Activity.id)
        .filter(Activity.status == STATUS_PUBLISHED, ActivityMember.confirmed.is_(True))
        .scalar()
        or 0
    )

    now = utc_naive_now()
    last_30 = now - timedelta(days=30)
    prev_30 = now - timedelta(days=60)
    recent_count = base.filter(Activity.activity_date >= last_30.date()).count()
    prev_count = base.filter(
        Activity.activity_date >= prev_30.date(), Activity.activity_date < last_30.date()
    ).count()
    growth = 0
    if prev_count:
        growth = round((recent_count - prev_count) / prev_count * 100)
    elif recent_count:
        growth = 100

    commission_stats = []
    for commission in (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order)
        .all()
    ):
        activity_count = base.filter(
            Activity.commissions.any(Commission.id == commission.id)
        ).count()
        member_count = (
            db.query(Member)
            .filter(Member.commission_id == commission.id, Member.is_active.is_(True))
            .count()
        )
        commission_stats.append(
            {
                "commission": commission,
                "activities": activity_count,
                "members": member_count,
            }
        )

    category_rows = (
        base.with_entities(Activity.category, func.count(Activity.id))
        .group_by(Activity.category)
        .order_by(func.count(Activity.id).desc())
        .all()
    )
    category_total = sum(row[1] for row in category_rows) or 1
    category_stats = [
        {
            "name": row[0] or "Lainnya",
            "count": row[1],
            "percent": round(row[1] / category_total * 100),
        }
        for row in category_rows[:6]
    ]

    months = date_range_last_months(6)
    month_counts = {key: 0 for key in months}
    earliest = date(months[0][0], months[0][1], 1)
    rows = (
        base.with_entities(Activity.activity_date).filter(Activity.activity_date >= earliest).all()
    )
    for (activity_date,) in rows:
        key = (activity_date.year, activity_date.month)
        if key in month_counts:
            month_counts[key] += 1
    max_month = max(month_counts.values()) or 1
    monthly = [
        {
            "label": month_label(year, month),
            "count": month_counts[(year, month)],
            "height": max(6, round(month_counts[(year, month)] / max_month * 100)),
        }
        for year, month in months
    ]

    top_members = (
        db.query(Member, func.count(ActivityMember.id).label("total"))
        .join(ActivityMember, ActivityMember.member_id == Member.id)
        .join(Activity, ActivityMember.activity_id == Activity.id)
        .filter(Activity.status == STATUS_PUBLISHED, ActivityMember.confirmed.is_(True))
        .group_by(Member.id)
        .order_by(func.count(ActivityMember.id).desc(), Member.full_name)
        .limit(5)
        .all()
    )

    recent_activities = (
        base.order_by(Activity.activity_date.desc(), Activity.id.desc()).limit(6).all()
    )

    photo_status = dict(
        db.query(ActivityPhoto.status, func.count(ActivityPhoto.id))
        .group_by(ActivityPhoto.status)
        .all()
    )

    return {
        "total_activities": total_activities,
        "published": published,
        "total_members": total_members,
        "total_photos": total_photos,
        "recognized_faces": recognized,
        "recent_count": recent_count,
        "growth": growth,
        "commission_stats": commission_stats,
        "category_stats": category_stats,
        "monthly": monthly,
        "top_members": top_members,
        "recent_activities": recent_activities,
        "photo_status": photo_status,
        "storage_bytes": media_size_bytes(),
        "today": local_now().date(),
    }


def public_guide_stats(db: Session) -> dict:
    """Angka ringkas untuk sampul panduan di halaman login (tanpa data privat)."""
    return {
        "total_activities": db.query(Activity)
        .filter(Activity.status == STATUS_PUBLISHED)
        .count(),
        "total_photos": db.query(ActivityPhoto)
        .join(Activity, ActivityPhoto.activity_id == Activity.id)
        .filter(Activity.status == STATUS_PUBLISHED)
        .count(),
        "total_members": db.query(Member).filter(Member.is_active.is_(True)).count(),
        "commission_stats": db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order)
        .all(),
    }


def user_stats(db: Session) -> dict:
    return {
        "users": db.query(User).count(),
        "active_users": db.query(User).filter(User.is_active.is_(True)).count(),
        "audit_entries": db.query(AuditLog).count(),
    }
