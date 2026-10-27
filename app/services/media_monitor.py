"""Orkestrasi pemindaian sentimen media online untuk satu anggota dewan.

Alur: Tavily mencari pemberitaan, Gemini menilai relevansi dan sentimen dengan
konteks, lalu hasil Gemini dipadukan dengan leksikon lokal. Bila Gemini tidak
tersedia, pemindaian tetap berjalan memakai leksikon saja.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

from ..config import settings
from ..models import MediaMention, Member, SentimentRun, User, utcnow
from . import gemini, tavily
from .sentiment import SentimentResult, analyze_sentiment, label_from_score

logger = logging.getLogger("sidewa.media_monitor")


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def _blend_analysis(
    ai: gemini.NewsAnalysis, lexicon: SentimentResult
) -> tuple[str, float, list[str]]:
    """Padukan skor Gemini dan leksikon, lalu jaga konsistensi label/skor."""
    weight = max(0.0, min(1.0, settings.gemini_score_weight))
    score = weight * ai.score + (1.0 - weight) * lexicon.score
    label = ai.label if ai.label in {"positif", "netral", "negatif"} else label_from_score(score)
    if label == "positif":
        score = max(score, 0.13)
    elif label == "negatif":
        score = min(score, -0.13)
    else:
        score = max(-0.11, min(0.11, score))
    keywords = list(dict.fromkeys([*ai.keywords, *lexicon.keywords]))[:6]
    return label, round(max(-1.0, min(1.0, score)), 4), keywords


def _search_query(member: Member) -> str:
    fallback = tavily.build_query(member)
    if not settings.gemini_configured or not settings.gemini_refine_query:
        return fallback
    return gemini.build_search_query(member, fallback=fallback)


def run_member_sentiment(
    db: Session,
    member: Member,
    *,
    actor: User,
    max_results: int | None = None,
    days: int | None = None,
) -> SentimentRun:
    """Cari pemberitaan via Tavily, analisis dengan Gemini + leksikon, lalu simpan.

    Melempar ``tavily.TavilyError`` bila konfigurasi atau jaringan Tavily
    bermasalah. Kegagalan Gemini tidak menggagalkan pemindaian: hasil leksikon
    tetap dipakai. Riwayat kegagalan Tavily tetap disimpan agar dashboard dapat
    menampilkan status.
    """
    query = _search_query(member)
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

    ai_analyses: dict[int, gemini.NewsAnalysis] = {}
    if settings.gemini_configured and settings.gemini_analysis_enabled and results:
        try:
            ai_analyses = gemini.analyze_news(member, results)
        except gemini.GeminiError as exc:
            logger.warning("Analisis Gemini gagal, beralih ke leksikon: %s", exc)

    counts = {"positif": 0, "netral": 0, "negatif": 0}
    score_total = 0.0
    stored = 0
    filtered = 0
    ai_used = 0
    fetched_at = utcnow()
    for index, item in enumerate(results):
        lexicon = analyze_sentiment(item.get("title", ""), item.get("snippet", ""))
        ai = ai_analyses.get(index)
        if ai is not None and not ai.relevant and settings.gemini_filter_irrelevant:
            filtered += 1
            continue

        if ai is not None and ai.relevant:
            label, score, keywords = _blend_analysis(ai, lexicon)
            provider = "tavily+gemini"
            ai_used += 1
        else:
            label, score, keywords = lexicon.label, lexicon.score, lexicon.keywords
            provider = "tavily"

        counts[label] = counts.get(label, 0) + 1
        score_total += score
        stored += 1
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
        mention.sentiment = label
        mention.sentiment_score = score
        mention.keywords = keywords
        mention.provider = provider
        mention.fetched_by_id = actor.id
        mention.fetched_at = fetched_at

    run.status = "success"
    run.error = None
    run.result_count = stored
    run.positive_count = counts["positif"]
    run.neutral_count = counts["netral"]
    run.negative_count = counts["negatif"]
    run.average_score = round(score_total / stored, 4) if stored else 0.0
    db.commit()
    if filtered or ai_used:
        logger.info(
            "Sentimen %s: %s tersimpan, %s dianalisis Gemini, %s tidak relevan dibuang",
            member.full_name,
            stored,
            ai_used,
            filtered,
        )
    return run
