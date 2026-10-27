"""Pengujian resolusi identitas anggota dewan."""

from __future__ import annotations

import json
from datetime import datetime


class _Commission:
    code = "III"
    bidang = "Pendidikan, Kesehatan"


class _Member:
    id = 42
    full_name = "H. Budi Santoso, S.H., M.H."
    position = "Anggota DPRD"
    party = "Partai Uji"
    dapil = "Riau I"
    commission = _Commission()
    portrait_path = "members/42.jpg"


def _identity(monkeypatch, tmp_path, overrides: dict | None = None):
    from app.config import settings
    from app.services import identity

    path = tmp_path / "member_identity.json"
    path.write_text(
        json.dumps({"members": overrides or {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "member_identity_file", path)
    return identity, identity.resolve_identity(_Member())


def test_name_variants_strip_titles_and_degrees():
    from app.services.identity import name_variants

    variants = name_variants("H. Budi Santoso, S.H., M.H.")
    lowered = {variant.casefold() for variant in variants}

    assert "budi santoso" in lowered
    assert "budi santoso s h m h" in lowered or any(
        variant.startswith("Budi Santoso") for variant in variants
    )
    assert all(len(variant) >= 3 for variant in variants)
    assert "h" not in lowered


def test_name_variants_include_aliases_and_short_forms():
    from app.services.identity import name_variants

    variants = name_variants("Budi Santoso", ["Budi S.", "Bang Budi"])
    lowered = {variant.casefold() for variant in variants}

    assert "budi santoso" in lowered
    assert "budi s." in lowered
    assert "bang budi" in lowered


def test_resolve_identity_from_member_and_settings(monkeypatch, tmp_path):
    _, resolved = _identity(monkeypatch, tmp_path)

    assert resolved.member_id == 42
    assert "Budi Santoso" in resolved.names
    assert resolved.institution == "DPRD Provinsi Riau"
    assert resolved.location == "Riau I"
    assert resolved.position == "Anggota DPRD"
    assert resolved.party == "Partai Uji"
    assert resolved.commission.startswith("Komisi III")
    assert resolved.organizations == ["Partai Uji"]
    assert resolved.photo_reference == "/media/members/42.jpg"
    assert resolved.year_from >= 2024
    assert resolved.year_to >= resolved.year_from


def test_resolve_identity_applies_file_overrides(monkeypatch, tmp_path):
    _, resolved = _identity(
        monkeypatch,
        tmp_path,
        {
            "42": {
                "aliases": ["Budi S."],
                "institution": "DPRD Provinsi Riau",
                "location": "Pekanbaru",
                "position": "Anggota Komisi III",
                "organizations": ["Partai Uji", "Ormas Uji"],
                "year_from": 2022,
                "year_to": 2027,
                "official_accounts": [
                    "https://instagram.com/budisantoso",
                    "https://www.facebook.com/budisantoso",
                ],
                "photo_url": "https://contoh.test/budi.jpg",
                "notes": "Anggota DPRD Riau periode 2024-2029.",
            }
        },
    )

    assert "Budi S." in resolved.names
    assert resolved.location == "Pekanbaru"
    assert resolved.position == "Anggota Komisi III"
    assert resolved.organizations == ["Partai Uji", "Ormas Uji"]
    assert resolved.year_from == 2022
    assert resolved.year_to == 2027
    assert resolved.photo_reference == "https://contoh.test/budi.jpg"
    assert resolved.official_domains == ["instagram.com", "facebook.com"]
    assert "periode 2024-2029" in resolved.prompt_block()


def test_identity_year_validity(monkeypatch, tmp_path):
    _, resolved = _identity(
        monkeypatch, tmp_path, {"42": {"year_from": 2024, "year_to": 2026}}
    )

    assert resolved.year_valid(datetime(2025, 5, 1))
    assert not resolved.year_valid(datetime(2023, 12, 31))
    assert not resolved.year_valid(datetime(2027, 1, 1))
    assert resolved.year_valid(None)


def test_out_of_region_hint_detects_other_regions(monkeypatch, tmp_path):
    identity, resolved = _identity(monkeypatch, tmp_path)

    assert identity.article_has_out_of_region_hint(
        "Anggota DPRD Jawa Barat Budi Santoso beri bantuan",
        "Bantuan disalurkan di Bandung.",
        resolved,
    )
    assert identity.article_has_out_of_region_hint(
        "DPR RI membahas anggaran", "Budi Santoso hadir.", resolved
    )
    assert not identity.article_has_out_of_region_hint(
        "Anggota DPRD Riau Budi Santoso beri bantuan",
        "Bantuan disalurkan di Pekanbaru.",
        resolved,
    )
