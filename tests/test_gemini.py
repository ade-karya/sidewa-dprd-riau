"""Pengujian integrasi Gemini untuk analisis sentimen pemberitaan."""

from __future__ import annotations

import pytest


class _Member:
    full_name = "Budi Santoso"
    position = "Anggota DPRD"
    party = "Partai Uji"
    dapil = "Riau I"
    commission = None


def _item(index: int) -> dict:
    return {
        "title": f"Berita {index}",
        "url": f"https://contoh.test/{index}",
        "source": "contoh.test",
        "snippet": "Kutipan berita.",
        "published_at": None,
    }


def test_gemini_analyze_news_maps_response(monkeypatch):
    from app.config import settings
    from app.services import gemini

    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    prompts: list[str] = []

    def fake_call(prompt, schema, **_kwargs):
        prompts.append(prompt)
        return {
            "analyses": [
                {
                    "index": 0,
                    "relevant": True,
                    "sentiment": "positif",
                    "score": 0.82,
                    "keywords": ["Kinerja", "APBD", "kinerja"],
                    "reason": "Kinerja anggota diapresiasi",
                }
            ]
        }

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    result = gemini.analyze_news(_Member(), [_item(0)])

    assert set(result) == {0}
    assert result[0].label == "positif"
    assert result[0].score == pytest.approx(0.82)
    assert result[0].keywords == ["kinerja", "apbd"]
    assert "Budi Santoso" in prompts[0]


def test_gemini_analyze_news_converts_batch_indices(monkeypatch):
    from app.config import settings
    from app.services import gemini

    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    calls = {"n": 0}

    def fake_call(_prompt, _schema, **_kwargs):
        calls["n"] += 1
        return {
            "analyses": [
                {
                    "index": 0,
                    "relevant": True,
                    "sentiment": "netral",
                    "score": 0.0,
                    "keywords": [],
                    "reason": "Informatif",
                }
            ]
        }

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    result = gemini.analyze_news(_Member(), [_item(i) for i in range(9)])

    assert calls["n"] == 2
    assert set(result) == {0, 8}


def test_gemini_query_falls_back_when_name_missing(monkeypatch):
    from app.config import settings
    from app.services import gemini

    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    monkeypatch.setattr(
        gemini,
        "_call_gemini",
        lambda *_args, **_kwargs: {"query": "berita politik daerah terbaru"},
    )
    query = gemini.build_search_query(_Member(), fallback='"Budi Santoso" DPRD Riau')
    assert query == '"Budi Santoso" DPRD Riau'


def test_run_member_sentiment_uses_gemini_and_filters_irrelevant(seeded_client, monkeypatch):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import MediaMention, Member, User
    from app.services import gemini, media_monitor, tavily

    _, _ = seeded_client
    results = [
        {
            "title": "Kinerja anggota DPRD Riau diapresiasi",
            "url": "https://contoh.test/gemini-positif",
            "source": "contoh.test",
            "snippet": "Warga menilai kinerjanya baik.",
            "published_at": None,
        },
        {
            "title": "DPRD Riau membahas anggaran",
            "url": "https://contoh.test/gemini-tidak-relevan",
            "source": "contoh.test",
            "snippet": "Rapat paripurna membahas APBD.",
            "published_at": None,
        },
    ]
    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    monkeypatch.setattr(tavily, "search_news", lambda *args, **kwargs: results)
    monkeypatch.setattr(
        gemini,
        "build_search_query",
        lambda _member, *, fallback: f'"uji" {fallback}',
    )

    def fake_analyze(_member, _results):
        return {
            0: gemini.NewsAnalysis(
                index=0,
                relevant=True,
                label="negatif",
                score=-0.9,
                keywords=["kinerja", "kritik"],
            ),
            1: gemini.NewsAnalysis(
                index=1,
                relevant=False,
                label="netral",
                score=0.0,
            ),
        }

    monkeypatch.setattr(gemini, "analyze_news", fake_analyze)

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None

        run = media_monitor.run_member_sentiment(db, member, actor=actor)
        assert run.status == "success"
        assert run.result_count == 1
        assert run.negative_count == 1
        assert run.average_score < 0

        mention = (
            db.query(MediaMention)
            .filter(MediaMention.member_id == member.id)
            .filter(MediaMention.url == "https://contoh.test/gemini-positif")
            .one()
        )
        assert mention.provider == "tavily+gemini"
        assert mention.sentiment == "negatif"
        assert mention.sentiment_score < 0
        assert "kritik" in (mention.keywords or [])

        from app.services.member_analytics import member_sentiment_summary

        summary = member_sentiment_summary(db, member)
        assert summary["gemini_mentions"] == 1
        assert summary["total"] == 1
    finally:
        db.close()


def test_run_member_sentiment_falls_back_to_lexicon(seeded_client, monkeypatch):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import MediaMention, Member, User
    from app.services import gemini, media_monitor, tavily

    _, _ = seeded_client
    results = [
        {
            "title": "Anggota DPRD Riau diapresiasi warga",
            "url": "https://contoh.test/fallback-positif",
            "source": "contoh.test",
            "snippet": "Kinerja baik dan responsif.",
            "published_at": None,
        }
    ]
    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    monkeypatch.setattr(tavily, "search_news", lambda *args, **kwargs: results)
    monkeypatch.setattr(
        gemini, "build_search_query", lambda _member, *, fallback: fallback
    )

    def fail(*_args, **_kwargs):
        raise gemini.GeminiError("Gemini tidak dapat dihubungi.")

    monkeypatch.setattr(gemini, "analyze_news", fail)

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None

        run = media_monitor.run_member_sentiment(db, member, actor=actor)
        assert run.status == "success"
        assert run.result_count == 1
        assert run.positive_count == 1

        mention = (
            db.query(MediaMention)
            .filter(MediaMention.member_id == member.id)
            .filter(MediaMention.url == "https://contoh.test/fallback-positif")
            .one()
        )
        assert mention.provider == "tavily"
        assert mention.sentiment == "positif"
    finally:
        db.close()
