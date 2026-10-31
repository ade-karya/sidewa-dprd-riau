"""Pengujian ringkasan gaya pada skill bersama rilis."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services import release_skills


def _release(**overrides):
    data = {
        "title": "DPRD Riau Sahkan APBD 2026 untuk Infrastruktur dan Kesejahteraan",
        "summary": "DPRD Provinsi Riau mengesahkan APBD 2026 dengan fokus infrastruktur.",
        "body": (
            "PEKANBARU — DPRD Riau mengesahkan APBD 2026.\n\n"
            '"Anggaran ini untuk rakyat," kata Ketua DPRD.\n\n'
            "Pembahasan berlangsung sejak pagi."
        ),
        "release_date": date(2026, 10, 30),
        "tag_list": ["DPRD Riau", "APBD 2026"],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_learning_text_mengikuti_rilis_terbit():
    text = release_skills._learning_text([_release(), _release()])

    assert "Basis belajar: 2 rilis" in text
    assert "Tag tersering: DPRD Riau (2)" in text
    assert "Contoh judul terbaru:" in text


def test_learning_text_kosong_memberi_panduan_dasar():
    assert release_skills._learning_text([]) == release_skills.DEFAULT_LEARNED
