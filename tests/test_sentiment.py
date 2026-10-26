"""Pengujian analisis sentimen lokal dan integrasi Tavily."""

import pytest


def test_analyze_sentiment_labels():
    from app.services.sentiment import analyze_sentiment, label_from_score

    positive = analyze_sentiment("Anggota DPRD diapresiasi warga")
    assert positive.label == "positif"
    assert positive.score > 0

    negative = analyze_sentiment("Anggota dikritik karena korupsi")
    assert negative.label == "negatif"
    assert negative.score < 0

    neutral = analyze_sentiment("Rapat paripurna membahas anggaran daerah")
    assert neutral.label == "netral"
    assert neutral.score == 0

    assert label_from_score(0.5) == "positif"
    assert label_from_score(-0.5) == "negatif"
    assert label_from_score(0.0) == "netral"


def test_tavily_requires_configuration(monkeypatch):
    from app.config import settings
    from app.services import tavily

    monkeypatch.setattr(settings, "tavily_api_key", "")
    with pytest.raises(tavily.TavilyError):
        tavily.search_news("uji")


def test_run_member_sentiment_persists_and_deduplicates(seeded_client, monkeypatch):
    from app.database import SessionLocal
    from app.models import MediaMention, Member, SentimentRun, User
    from app.services import media_monitor, tavily

    _, _ = seeded_client
    results = [
        {
            "title": "Anggota DPRD Riau diapresiasi",
            "url": "https://contoh.test/satu",
            "source": "contoh.test",
            "snippet": "Kinerja baik dan responsif.",
            "published_at": None,
        },
        {
            "title": "Anggota dikritik karena tidak hadir",
            "url": "https://contoh.test/dua",
            "source": "contoh.test",
            "snippet": "Warga kecewa dengan kinerjanya.",
            "published_at": None,
        },
    ]
    monkeypatch.setattr(tavily, "search_news", lambda *args, **kwargs: results)

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None

        run = media_monitor.run_member_sentiment(db, member, actor=actor)
        assert run.status == "success"
        assert run.result_count == 2
        assert run.positive_count == 1
        assert run.negative_count == 1
        assert run.average_score < 1

        first_count = (
            db.query(MediaMention).filter(MediaMention.member_id == member.id).count()
        )
        assert first_count == 2

        media_monitor.run_member_sentiment(db, member, actor=actor)
        second_count = (
            db.query(MediaMention).filter(MediaMention.member_id == member.id).count()
        )
        assert second_count == 2
        assert db.query(SentimentRun).filter(SentimentRun.member_id == member.id).count() == 2
    finally:
        db.close()


def test_run_member_sentiment_records_failure(seeded_client, monkeypatch):
    from app.database import SessionLocal
    from app.models import Member, SentimentRun, User
    from app.services import media_monitor, tavily

    _, _ = seeded_client

    def _fail(*args, **kwargs):
        raise tavily.TavilyError("Kuota Tavily habis.")

    monkeypatch.setattr(tavily, "search_news", _fail)

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None
        with pytest.raises(tavily.TavilyError):
            media_monitor.run_member_sentiment(db, member, actor=actor)

        run = (
            db.query(SentimentRun)
            .filter(SentimentRun.member_id == member.id)
            .order_by(SentimentRun.id.desc())
            .first()
        )
        assert run is not None
        assert run.status == "failed"
        assert "Kuota" in (run.error or "")
    finally:
        db.close()
