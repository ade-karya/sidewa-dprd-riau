"""Agregasi data dashboard per anggota dewan.

Dua sumber data utama:
1. Publikasi & dokumentasi Humas (tabel activities, activity_photos,
   activity_members).
2. Sentimen pemberitaan media online hasil pencarian Tavily (tabel
   media_mentions, sentiment_runs).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..constants import ROLE_HUMAS, STATUS_PUBLISHED
from ..models import (
    Activity,
    ActivityMember,
    ActivityPhoto,
    MediaMention,
    Member,
    SentimentRun,
    User,
)
from ..utils import date_range_last_months, local_now, month_label, utc_naive_now
from .search import visible_query

SENTIMENT_LABELS = {
    "positif": "Positif",
    "netral": "Netral",
    "negatif": "Negatif",
}

SENTIMENT_TONES = {
    "positif": "green",
    "netral": "gold",
    "negatif": "red",
}

# Tugas dan fungsi umum DPRD yang relevan untuk seluruh anggota.
TUGAS_DEWAN = [
    {
        "title": "Legislasi",
        "text": (
            "Membentuk Peraturan Daerah bersama kepala daerah, termasuk mengusulkan "
            "inisiatif dan menampung aspirasi masyarakat."
        ),
    },
    {
        "title": "Anggaran",
        "text": (
            "Menyusun dan menetapkan APBD bersama pemerintah daerah, serta mengawasi "
            "realisasi belanja dan pendapatan daerah."
        ),
    },
    {
        "title": "Pengawasan",
        "text": (
            "Mengawasi pelaksanaan peraturan daerah, kebijakan pemerintah daerah, dan "
            "penggunaan anggaran agar tepat sasaran."
        ),
    },
    {
        "title": "Aspirasi rakyat",
        "text": (
            "Menyerap dan menindaklanjuti aspirasi masyarakat melalui reses, audiensi, "
            "rapat dengar pendapat, dan kunjungan kerja."
        ),
    },
]


def _activity_base(db: Session, member: Member, viewer: User):
    return visible_query(db, viewer).filter(
        Activity.member_links.any(ActivityMember.member_id == member.id)
    )


def _monthly_counts(dates: list[date], months: int = 6) -> list[dict]:
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


def _category_stats(db: Session, base) -> list[dict]:
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


def _sentiment_monthly(mentions: list[MediaMention], months: int = 6) -> list[dict]:
    keys = date_range_last_months(months)
    buckets: dict[tuple[int, int], list[float]] = {key: [] for key in keys}
    for mention in mentions:
        value = mention.published_at or mention.fetched_at
        if not value:
            continue
        key = (value.year, value.month)
        if key in buckets:
            buckets[key].append(mention.sentiment_score or 0.0)
    maximum = max((len(bucket) for bucket in buckets.values()), default=0) or 1
    return [
        {
            "label": month_label(year, month),
            "count": len(buckets[(year, month)]),
            "height": max(6, round(len(buckets[(year, month)]) / maximum * 100)),
            "score": round(sum(buckets[(year, month)]) / len(buckets[(year, month)]), 3)
            if buckets[(year, month)]
            else 0.0,
        }
        for year, month in keys
    ]


def _sentiment_from_mentions(
    mentions: list[MediaMention],
    latest_run: SentimentRun | None = None,
    *,
    limit: int = 8,
) -> dict:
    counts = Counter(mention.sentiment for mention in mentions)
    total = len(mentions)
    average = round(
        sum(mention.sentiment_score or 0.0 for mention in mentions) / total, 3
    ) if total else 0.0
    positive = counts.get("positif", 0)
    neutral = counts.get("netral", 0)
    negative = counts.get("negatif", 0)
    keywords = Counter()
    sources = Counter()
    for mention in mentions:
        for keyword in mention.keywords or []:
            keywords[keyword] += 1
        if mention.source:
            sources[mention.source] += 1
    gauge = round((average + 1.0) / 2.0 * 100)
    if average >= 0.12:
        tone = "positif"
        tone_label = "Cenderung positif"
    elif average <= -0.12:
        tone = "negatif"
        tone_label = "Cenderung negatif"
    else:
        tone = "netral"
        tone_label = "Cenderung netral"
    last_updated = max(
        (mention.fetched_at for mention in mentions if mention.fetched_at),
        default=None,
    )
    return {
        "has_data": total > 0,
        "total": total,
        "mentions": mentions[:limit],
        "latest_run": latest_run,
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "positive_pct": round(positive / total * 100) if total else 0,
        "neutral_pct": round(neutral / total * 100) if total else 0,
        "negative_pct": round(negative / total * 100) if total else 0,
        "average_score": average,
        "score_display": f"{average:+.2f}".replace(".", ","),
        "gauge": max(0, min(100, gauge)),
        "tone": tone,
        "tone_label": tone_label,
        "keywords": [{"name": name, "count": count} for name, count in keywords.most_common(8)],
        "sources": [{"name": name, "count": count} for name, count in sources.most_common(6)],
        "monthly": _sentiment_monthly(mentions),
        "last_updated": last_updated,
    }


def member_sentiment_summary(
    db: Session, member: Member, *, limit: int = 8
) -> dict:
    mentions = (
        db.query(MediaMention)
        .filter(MediaMention.member_id == member.id)
        .order_by(
            func.coalesce(MediaMention.published_at, MediaMention.fetched_at).desc(),
            MediaMention.id.desc(),
        )
        .all()
    )
    latest_run = (
        db.query(SentimentRun)
        .filter(SentimentRun.member_id == member.id)
        .order_by(SentimentRun.created_at.desc(), SentimentRun.id.desc())
        .first()
    )
    return _sentiment_from_mentions(mentions, latest_run, limit=limit)


def _sentiment_rows_for_members(db: Session, member_ids: list[int]) -> dict[int, dict]:
    if not member_ids:
        return {}
    rows = (
        db.query(
            MediaMention.member_id,
            MediaMention.sentiment,
            func.count(MediaMention.id),
            func.avg(MediaMention.sentiment_score),
        )
        .filter(MediaMention.member_id.in_(member_ids))
        .group_by(MediaMention.member_id, MediaMention.sentiment)
        .all()
    )
    grouped: dict[int, dict] = defaultdict(
        lambda: {"positif": 0, "netral": 0, "negatif": 0, "total": 0, "score_sum": 0.0}
    )
    for member_id, label, count, average in rows:
        bucket = grouped[member_id]
        bucket[label] = int(count or 0)
        bucket["total"] += int(count or 0)
        bucket["score_sum"] += float(average or 0.0) * int(count or 0)
    result: dict[int, dict] = {}
    for member_id, bucket in grouped.items():
        total = bucket["total"]
        average = round(bucket["score_sum"] / total, 3) if total else 0.0
        result[member_id] = {
            "total": total,
            "positive": bucket["positif"],
            "neutral": bucket["netral"],
            "negative": bucket["negatif"],
            "average_score": average,
            "tone": "positif"
            if average >= 0.12
            else "negatif"
            if average <= -0.12
            else "netral",
            "gauge": max(0, min(100, round((average + 1.0) / 2.0 * 100))),
        }
    return result


def sentiment_overview(db: Session, members: list[Member]) -> list[dict]:
    ids = [member.id for member in members]
    rows = _sentiment_rows_for_members(db, ids)
    runs = (
        db.query(SentimentRun)
        .filter(SentimentRun.member_id.in_(ids))
        .order_by(SentimentRun.created_at.desc(), SentimentRun.id.desc())
        .all()
        if ids
        else []
    )
    latest_run: dict[int, SentimentRun] = {}
    for run in runs:
        latest_run.setdefault(run.member_id, run)
    result = []
    for member in members:
        summary = rows.get(member.id) or {
            "total": 0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "average_score": 0.0,
            "tone": "netral",
            "gauge": 50,
        }
        result.append(
            {
                "member": member,
                "summary": summary,
                "latest_run": latest_run.get(member.id),
            }
        )
    return result


def member_dashboard_data(db: Session, member: Member, viewer: User) -> dict:
    base = _activity_base(db, member, viewer)
    total_activities = base.count()
    published = base.filter(Activity.status == STATUS_PUBLISHED).count()

    photo_query = (
        db.query(ActivityPhoto)
        .join(Activity, ActivityPhoto.activity_id == Activity.id)
        .filter(
            Activity.status == STATUS_PUBLISHED,
            Activity.member_links.any(ActivityMember.member_id == member.id),
        )
    )
    photo_count = photo_query.count()

    recognized = (
        db.query(func.count(ActivityMember.id))
        .join(Activity, ActivityMember.activity_id == Activity.id)
        .filter(
            Activity.status == STATUS_PUBLISHED,
            ActivityMember.member_id == member.id,
            ActivityMember.confirmed.is_(True),
        )
        .scalar()
        or 0
    )

    humas_base = base.join(User, Activity.created_by_id == User.id).filter(
        User.role == ROLE_HUMAS
    )
    humas_publications = humas_base.count()

    now = utc_naive_now()
    recent_count = base.filter(Activity.activity_date >= (now - timedelta(days=90)).date()).count()
    last_activity_date = (
        base.with_entities(func.max(Activity.activity_date)).scalar()
    )
    dates = [
        row[0]
        for row in base.with_entities(Activity.activity_date)
        .order_by(Activity.activity_date.desc())
        .all()
    ]
    monthly = _monthly_counts(dates)
    category_stats = _category_stats(db, base)

    recent_activities = (
        base.order_by(Activity.activity_date.desc(), Activity.id.desc()).limit(6).all()
    )
    humas_activities = (
        humas_base.order_by(Activity.activity_date.desc(), Activity.id.desc()).limit(4).all()
    )

    commission_ids: set[int] = set()
    for activity in recent_activities:
        commission_ids.update(activity.all_commission_ids)

    sentiment = member_sentiment_summary(db, member)
    face_login = member.face_logins[0] if member.face_logins else None
    account = member.account

    return {
        "member": member,
        "activity_count": total_activities,
        "published_count": published,
        "photo_count": photo_count,
        "recognized_count": recognized,
        "humas_publication_count": humas_publications,
        "recent_count": recent_count,
        "last_activity_date": last_activity_date,
        "monthly": monthly,
        "category_stats": category_stats,
        "recent_activities": recent_activities,
        "humas_activities": humas_activities,
        "commission_ids": sorted(commission_ids),
        "sentiment": sentiment,
        "face_login": face_login,
        "member_account": account,
        "tugas_dewan": TUGAS_DEWAN,
        "today": local_now().date(),
    }
