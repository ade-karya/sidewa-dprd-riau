"""Utilitas siaran pers (rilis) Humas.

Rilis adalah kanal publikasi teks yang melengkapi dokumentasi foto kegiatan.
Rilis dapat ditautkan ke satu kegiatan, memiliki status draf/terbit/arsip, dan
hanya terlihat oleh seluruh pengguna setelah diterbitkan.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from ..constants import CONTENT_MANAGER_ROLES, STATUS_PUBLISHED, STATUSES
from ..models import Activity, PressRelease, User


def slugify(value: str) -> str:
    """Ubah judul menjadi slug URL yang aman dan stabil."""
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:180].rstrip("-") or "rilis")


def unique_slug(db: Session, title: str, *, exclude_id: int | None = None) -> str:
    base = slugify(title)
    candidate = base
    counter = 2
    while True:
        query = db.query(PressRelease.id).filter(PressRelease.slug == candidate)
        if exclude_id is not None:
            query = query.filter(PressRelease.id != exclude_id)
        if query.first() is None:
            return candidate
        suffix = f"-{counter}"
        candidate = f"{base[: 180 - len(suffix)]}{suffix}"
        counter += 1


def next_code(db: Session, year: int) -> str:
    """Nomor rilis berurutan per tahun, mis. RIL-2026-0001."""
    prefix = f"RIL-{year}-"
    existing = {
        code
        for (code,) in db.query(PressRelease.code)
        .filter(PressRelease.code.like(prefix + "%"))
        .all()
    }
    counter = len(existing) + 1
    while f"{prefix}{counter:04d}" in existing:
        counter += 1
    return f"{prefix}{counter:04d}"


def visible_query(db: Session, user: User) -> Query:
    """Rilis terbit untuk semua pengguna; draf/arsip hanya untuk pengelola."""
    query = db.query(PressRelease)
    if user.role not in CONTENT_MANAGER_ROLES:
        query = query.filter(PressRelease.status == STATUS_PUBLISHED)
    return query


def apply_filters(
    query: Query,
    *,
    q: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    author_id: int | None = None,
    activity_id: int | None = None,
) -> Query:
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                PressRelease.title.ilike(like),
                PressRelease.summary.ilike(like),
                PressRelease.body.ilike(like),
                PressRelease.code.ilike(like),
                PressRelease.slug.ilike(like),
                PressRelease.activity.has(Activity.title.ilike(like)),
            )
        )
    if status:
        query = query.filter(PressRelease.status == status)
    if date_from:
        query = query.filter(PressRelease.release_date >= date_from)
    if date_to:
        query = query.filter(PressRelease.release_date <= date_to)
    if author_id is not None:
        query = query.filter(PressRelease.author_id == author_id)
    if activity_id is not None:
        query = query.filter(PressRelease.activity_id == activity_id)
    return query


def status_counts(query: Query) -> dict[str, int]:
    """Hitung jumlah rilis per status dari query dasar yang sudah difilter."""
    rows = (
        query.with_entities(PressRelease.status, func.count(PressRelease.id))
        .order_by(None)
        .group_by(PressRelease.status)
        .all()
    )
    counts = {status: 0 for status in STATUSES}
    for status, count in rows:
        counts[status] = count
    return counts
