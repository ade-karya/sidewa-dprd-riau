"""Agregasi dashboard dan ruang kerja staf Humas Sekretariat DPRD.

Setiap staf Humas memiliki dashboard pribadi yang menampilkan unggahan
dokumentasi, status Face ID, serta ringkasan pekerjaan tim Humas. Ruang kerja
(workspace) menyatukan draf, publikasi terbaru, dan pintasan tugas harian.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..constants import (
    ROLE_HUMAS,
    ROLE_STAF_HUMAS,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from ..models import (
    Activity,
    ActivityPhoto,
    HumasStaff,
    HumasStaffAccount,
    HumasStaffFaceLogin,
    User,
)
from ..utils import date_range_last_months, local_now, month_label, utc_naive_now

HUMAS_DUTIES = [
    {
        "title": "Dokumentasi kegiatan",
        "text": (
            "Mengabadikan rapat paripurna, rapat kerja, kunjungan kerja, reses, "
            "dan kegiatan kedewanan lainnya secara lengkap dan akurat."
        ),
    },
    {
        "title": "Publikasi informasi",
        "text": (
            "Menyusun rilis, takarir, dan konten media sosial agar kegiatan DPRD "
            "tersampaikan kepada masyarakat dengan bahasa yang mudah dipahami."
        ),
    },
    {
        "title": "Pengelolaan arsip",
        "text": (
            "Merapikan foto, metadata, dan dokumentasi kegiatan agar mudah ditelusuri "
            "oleh anggota dewan, staf komisi, dan pimpinan."
        ),
    },
    {
        "title": "Layanan perpustakaan",
        "text": (
            "Mendukung layanan perpustakaan Sekretariat DPRD, termasuk penelusuran "
            "dokumen dan bahan informasi kedewanan."
        ),
    },
]

WORKSPACE_SHORTCUTS = [
    {
        "label": "Seleksi foto AI",
        "description": "Kurasi foto terbaik sebelum diunggah.",
        "href": "/seleksi-foto",
        "icon": "sparkles",
        "tone": "purple",
    },
    {
        "label": "Unggah dokumentasi",
        "description": "Tambahkan kegiatan dan foto baru.",
        "href": "/kegiatan/baru",
        "icon": "upload",
        "tone": "purple",
    },
    {
        "label": "Kelola kegiatan",
        "description": "Sunting draf dan publikasi tim.",
        "href": "/kegiatan",
        "icon": "calendar",
        "tone": "blue",
    },
    {
        "label": "Cari wajah",
        "description": "Telusuri dokumentasi berdasarkan wajah.",
        "href": "/cari",
        "icon": "scan",
        "tone": "green",
    },
    {
        "label": "Direktori anggota",
        "description": "Buka data anggota dan komisi.",
        "href": "/anggota",
        "icon": "users",
        "tone": "gold",
    },
]


def _monthly_counts(dates: list, months: int = 6) -> list[dict]:
    keys = date_range_last_months(months)
    counts = {key: 0 for key in keys}
    for value in dates:
        if value is None:
            continue
        key = (value.year, value.month)
        if key in counts:
            counts[key] += 1
    maximum = max(counts.values()) or 1
    return [
        {
            "label": month_label(year, month),
            "count": counts[(year, month)],
            "height": max(6, round(counts[(year, month)] / maximum * 100)),
        }
        for year, month in keys
    ]


def _category_stats(base) -> list[dict]:
    rows = (
        base.with_entities(Activity.category, func.count(Activity.id))
        .group_by(Activity.category)
        .order_by(func.count(Activity.id).desc())
        .all()
    )
    total = sum(row[1] for row in rows) or 1
    return [
        {
            "name": row[0] or "Lainnya",
            "count": row[1],
            "percent": round(row[1] / total * 100),
        }
        for row in rows[:6]
    ]


def _team_base(db: Session):
    return (
        db.query(Activity)
        .join(User, Activity.created_by_id == User.id)
        .filter(User.role.in_([ROLE_HUMAS, ROLE_STAF_HUMAS]))
    )


def staff_dashboard_data(db: Session, staff: HumasStaff, viewer: User) -> dict:
    account = staff.account
    user = account.user if account else None
    base = db.query(Activity)
    if user:
        base = base.filter(Activity.created_by_id == user.id)
    else:
        base = base.filter(Activity.id < 0)

    total_activities = base.count()
    published = base.filter(Activity.status == STATUS_PUBLISHED).count()
    drafts = base.filter(Activity.status == STATUS_DRAFT).count()

    photo_count = 0
    if user:
        photo_count = (
            db.query(func.count(ActivityPhoto.id))
            .join(Activity, ActivityPhoto.activity_id == Activity.id)
            .filter(Activity.created_by_id == user.id)
            .scalar()
            or 0
        )

    now = utc_naive_now()
    recent_count = base.filter(
        Activity.activity_date >= (now - timedelta(days=30)).date()
    ).count()
    view_count = base.with_entities(func.coalesce(func.sum(Activity.view_count), 0)).scalar() or 0
    dates = [
        row[0]
        for row in base.with_entities(Activity.activity_date)
        .order_by(Activity.activity_date.desc())
        .all()
    ]
    monthly = _monthly_counts(dates)
    category_stats = _category_stats(base)

    recent_activities = (
        base.order_by(Activity.activity_date.desc(), Activity.id.desc()).limit(6).all()
    )
    draft_activities = (
        base.filter(Activity.status == STATUS_DRAFT)
        .order_by(Activity.updated_at.desc(), Activity.id.desc())
        .limit(5)
        .all()
    )
    last_activity_date = base.with_entities(func.max(Activity.activity_date)).scalar()

    team_base = _team_base(db)
    team_total = team_base.count()
    team_published = team_base.filter(Activity.status == STATUS_PUBLISHED).count()
    team_recent = (
        team_base.filter(Activity.status == STATUS_PUBLISHED)
        .order_by(Activity.activity_date.desc(), Activity.id.desc())
        .limit(5)
        .all()
    )

    staff_total = db.query(HumasStaff).filter(HumasStaff.is_active.is_(True)).count()
    staff_with_face = (
        db.query(func.count(func.distinct(HumasStaffFaceLogin.staff_id)))
        .join(HumasStaff, HumasStaffFaceLogin.staff_id == HumasStaff.id)
        .filter(
            HumasStaff.is_active.is_(True),
            HumasStaffFaceLogin.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    face_login = staff.faces[0] if staff.faces else None

    return {
        "staff": staff,
        "activity_count": total_activities,
        "published_count": published,
        "draft_count": drafts,
        "photo_count": photo_count,
        "recent_count": recent_count,
        "view_count": view_count,
        "last_activity_date": last_activity_date,
        "monthly": monthly,
        "category_stats": category_stats,
        "recent_activities": recent_activities,
        "draft_activities": draft_activities,
        "team_total": team_total,
        "team_published": team_published,
        "team_recent": team_recent,
        "staff_total": staff_total,
        "staff_with_face": staff_with_face,
        "face_login": face_login,
        "staff_account": account,
        "duties": HUMAS_DUTIES,
        "shortcuts": WORKSPACE_SHORTCUTS,
        "today": local_now().date(),
    }


def staff_overview(db: Session, staff_list: list[HumasStaff]) -> list[dict]:
    if not staff_list:
        return []
    ids = [staff.id for staff in staff_list]
    face_ids = {
        row[0]
        for row in db.query(HumasStaffFaceLogin.staff_id)
        .filter(
            HumasStaffFaceLogin.staff_id.in_(ids),
            HumasStaffFaceLogin.is_active.is_(True),
        )
        .all()
    }
    accounts = {
        row.staff_id: row
        for row in db.query(HumasStaffAccount)
        .filter(HumasStaffAccount.staff_id.in_(ids))
        .all()
    }
    user_ids = [account.user_id for account in accounts.values()]
    counts: Counter[int] = Counter()
    if user_ids:
        rows = (
            db.query(Activity.created_by_id, func.count(Activity.id))
            .filter(Activity.created_by_id.in_(user_ids))
            .group_by(Activity.created_by_id)
            .all()
        )
        counts = Counter({user_id: count for user_id, count in rows})
    result = []
    for staff in staff_list:
        account = accounts.get(staff.id)
        result.append(
            {
                "staff": staff,
                "face_active": staff.id in face_ids,
                "account": account,
                "activity_count": counts.get(account.user_id, 0) if account else 0,
            }
        )
    return result
