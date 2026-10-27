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

    def fake_analyze(_member, _results, **_kwargs):
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


def test_gemini_parses_identity_fields(monkeypatch):
    from app.config import settings
    from app.services import gemini

    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    prompts: list[str] = []

    def fake_call(prompt, _schema, **_kwargs):
        prompts.append(prompt)
        return {
            "analyses": [
                {
                    "index": 0,
                    "relevant": True,
                    "sentiment": "negatif",
                    "score": -0.7,
                    "keywords": ["kritik"],
                    "reason": "Dikritik soal anggaran",
                    "identity_score": 0.91,
                    "identity_evidence": ["DPRD Riau", "Pekanbaru"],
                    "identity_conflict": False,
                    "conflict_reason": "",
                    "year_valid": True,
                }
            ]
        }

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    result = gemini.analyze_news(_Member(), [_item(0)])

    analysis = result[0]
    assert analysis.identity_score == pytest.approx(0.91)
    assert analysis.identity_evidence == ["DPRD Riau", "Pekanbaru"]
    assert analysis.identity_conflict is False
    assert analysis.year_valid is True
    assert "RESOLUSI IDENTITAS" in prompts[0]
    assert "minimal DUA jangkar" in prompts[0]


def test_gemini_parses_identity_conflict(monkeypatch):
    from app.config import settings
    from app.services import gemini

    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    monkeypatch.setattr(
        gemini,
        "_call_gemini",
        lambda *_args, **_kwargs: {
            "analyses": [
                {
                    "index": 0,
                    "relevant": False,
                    "sentiment": "netral",
                    "score": 0.0,
                    "keywords": [],
                    "reason": "Nama sama, daerah berbeda",
                    "identity_score": 0.2,
                    "identity_evidence": ["DPRD Jawa Barat"],
                    "identity_conflict": True,
                    "conflict_reason": "Anggota DPRD Jawa Barat",
                    "year_valid": True,
                }
            ]
        },
    )

    result = gemini.analyze_news(_Member(), [_item(0)])

    assert result[0].identity_conflict is True
    assert result[0].conflict_reason == "Anggota DPRD Jawa Barat"
    assert result[0].identity_score == pytest.approx(0.2)


def _rejection_run(seeded_client, monkeypatch, analysis, published_at=None):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import MediaMention, Member, User
    from app.services import gemini, media_monitor, tavily

    _, _ = seeded_client
    results = [
        {
            "title": "Berita tentang anggota DPRD Riau",
            "url": "https://contoh.test/identitas",
            "source": "contoh.test",
            "snippet": "Kutipan berita.",
            "published_at": published_at,
        }
    ]
    monkeypatch.setattr(settings, "gemini_api_key", "uji")
    monkeypatch.setattr(tavily, "search_news", lambda *args, **kwargs: results)
    monkeypatch.setattr(
        gemini, "build_search_query", lambda _member, *, fallback: fallback
    )
    monkeypatch.setattr(
        gemini,
        "analyze_news",
        lambda _member, _items, **_kwargs: {0: analysis},
    )

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None

        run = media_monitor.run_member_sentiment(db, member, actor=actor)
        mentions = (
            db.query(MediaMention)
            .filter(MediaMention.member_id == member.id)
            .filter(MediaMention.url == "https://contoh.test/identitas")
            .all()
        )
        return run, mentions
    finally:
        db.close()


def test_run_member_sentiment_rejects_low_identity_score(
    seeded_client, monkeypatch
):
    from app.services import gemini

    analysis = gemini.NewsAnalysis(
        index=0,
        relevant=True,
        label="positif",
        score=0.8,
        identity_score=0.4,
    )
    run, mentions = _rejection_run(seeded_client, monkeypatch, analysis)

    assert run.status == "success"
    assert run.result_count == 0
    assert mentions == []


def test_run_member_sentiment_rejects_identity_conflict(
    seeded_client, monkeypatch
):
    from app.services import gemini

    analysis = gemini.NewsAnalysis(
        index=0,
        relevant=True,
        label="negatif",
        score=-0.6,
        identity_score=0.95,
        identity_conflict=True,
        conflict_reason="Anggota DPRD provinsi lain",
    )
    run, mentions = _rejection_run(seeded_client, monkeypatch, analysis)

    assert run.result_count == 0
    assert mentions == []


def test_run_member_sentiment_rejects_out_of_range_year(
    seeded_client, monkeypatch
):
    from app.services import gemini

    analysis = gemini.NewsAnalysis(
        index=0,
        relevant=True,
        label="positif",
        score=0.7,
        identity_score=0.9,
        year_valid=False,
    )
    run, mentions = _rejection_run(seeded_client, monkeypatch, analysis)

    assert run.result_count == 0
    assert mentions == []


def test_run_member_sentiment_rejects_out_of_region_without_gemini(
    seeded_client, monkeypatch
):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import MediaMention, Member, User
    from app.services import media_monitor, tavily

    _, _ = seeded_client
    results = [
        {
            "title": "Anggota DPRD Jawa Barat membahas anggaran",
            "url": "https://contoh.test/jabar",
            "source": "contoh.test",
            "snippet": "Rapat di Bandung.",
            "published_at": None,
        }
    ]
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(tavily, "search_news", lambda *args, **kwargs: results)

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).first()
        actor = db.query(User).filter(User.username == "superadmin").first()
        assert member is not None and actor is not None

        run = media_monitor.run_member_sentiment(db, member, actor=actor)
        assert run.status == "success"
        assert run.result_count == 0
        assert (
            db.query(MediaMention)
            .filter(MediaMention.url == "https://contoh.test/jabar")
            .count()
            == 0
        )
    finally:
        db.close()
