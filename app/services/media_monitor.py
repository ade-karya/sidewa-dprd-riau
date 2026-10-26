"""Orkestrasi pemindaian sentimen media online untuk satu anggota dewan."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..models import MediaMention, Member, SentimentRun, User, utcnow
from . import tavily
from .sentiment import analyze_sentiment


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def run_member_sentiment(
    db: Session,
    member: Member,
    *,
    actor: User,
    max_results: int | None = None,
    days: int | None = None,
) -> SentimentRun:
    """Cari pemberitaan via Tavily, simpan, dan hitung sentimennya.

    Melempar ``tavily.TavilyError`` bila konfigurasi atau jaringan bermasalah.
    Riwayat kegagalan tetap disimpan agar dashboard dapat menampilkan status.
    """
    query = tavily.build_query(member)
    run = SentimentRun(
        member_id=member.id,
        query=query,
        requested_by_id=actor.id,
        status="running",
    )
    db.add(run)
    db.flush()

    try:
        results = tavily.search_news(query, max_results=max_results, days=days)
    except tavily.TavilyError as exc:
        run.status = "failed"
        run.error = str(exc)[:500]
        run.result_count = 0
        db.commit()
        raise

    counts = {"positif": 0, "netral": 0, "negatif": 0}
    score_total = 0.0
    fetched_at = utcnow()
    for item in results:
        analysis = analyze_sentiment(item.get("title", ""), item.get("snippet", ""))
        counts[analysis.label] = counts.get(analysis.label, 0) + 1
        score_total += analysis.score
        url_hash = _url_hash(item["url"])
        mention = (
            db.query(MediaMention)
            .filter(
                MediaMention.member_id == member.id,
                MediaMention.url_hash == url_hash,
            )
            .first()
        )
        if mention is None:
            mention = MediaMention(
                member_id=member.id,
                url_hash=url_hash,
            )
            db.add(mention)
        mention.run_id = run.id
        mention.title = item.get("title", "")[:400]
        mention.url = item.get("url", "")
        mention.source = item.get("source", "")[:160]
        mention.snippet = item.get("snippet", "")
        mention.published_at = item.get("published_at")
        mention.sentiment = analysis.label
        mention.sentiment_score = analysis.score
        mention.keywords = analysis.keywords
        mention.provider = "tavily"
        mention.fetched_by_id = actor.id
        mention.fetched_at = fetched_at

    run.status = "success"
    run.error = None
    run.result_count = len(results)
    run.positive_count = counts["positif"]
    run.neutral_count = counts["netral"]
    run.negative_count = counts["negatif"]
    run.average_score = round(score_total / len(results), 4) if results else 0.0
    db.commit()
    return run
