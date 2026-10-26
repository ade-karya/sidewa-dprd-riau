"""Analisis sentimen sederhana untuk pemberitaan media online berbahasa Indonesia.

Modul ini sengaja tidak bergantung pada layanan AI eksternal. Skor dihitung
dari leksikon kata/frasa positif dan negatif, dengan penanganan negasi dasar.
Hasilnya dipakai sebagai indikator awal pada dashboard anggota dewan; admin
komisi tetap dapat membaca artikel aslinya melalui tautan sumber.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Bobot frasa. Frasa yang lebih spesifik diberi bobot lebih tinggi.
POSITIVE_TERMS: dict[str, int] = {
    "apresiasi": 3,
    "mengapresiasi": 3,
    "diapresiasi": 3,
    "dukungan": 2,
    "mendukung": 2,
    "kinerja baik": 3,
    "berhasil": 2,
    "transparan": 2,
    "akuntabel": 2,
    "responsif": 2,
    "peduli": 2,
    "memuaskan": 2,
    "terpuji": 3,
    "berprestasi": 2,
    "memperjuangkan": 2,
    "proaktif": 2,
    "inovatif": 2,
    "solutif": 2,
    "sinergi": 1,
    "kolaborasi": 1,
    "aspirasi": 1,
    "tegas": 1,
    "bersih": 1,
    "membangun": 1,
    "mendorong": 1,
    "setuju": 1,
    "menghargai": 1,
    "berkomitmen": 1,
    "manfaat": 1,
    "positif": 1,
    "membantu": 1,
    "ramah": 1,
    "cepat tanggap": 2,
}

NEGATIVE_TERMS: dict[str, int] = {
    "korupsi": 4,
    "gratifikasi": 4,
    "suap": 4,
    "nepotisme": 4,
    "skandal": 4,
    "penyimpangan": 3,
    "dituduh": 2,
    "dikritik": 2,
    "kritik": 1,
    "kecewa": 2,
    "mengecewakan": 3,
    "gagal": 2,
    "tidak transparan": 3,
    "tidak akuntabel": 3,
    "tidak hadir": 3,
    "absen": 2,
    "protes": 2,
    "demo": 1,
    "menolak": 1,
    "kontroversi": 2,
    "polemik": 2,
    "pelanggaran": 2,
    "sanksi": 2,
    "markup": 3,
    "lambat": 1,
    "disfungsi": 2,
    "ricuh": 2,
    "bentrok": 2,
    "kualitas buruk": 2,
    "tidak peduli": 2,
    "masalah": 1,
    "konflik": 1,
    "tuntut": 1,
    "desakan": 1,
    "sorotan": 1,
    "didesak": 2,
    "dipertanyakan": 2,
}

NEGATIONS = {"tidak", "bukan", "belum", "tanpa", "kurang", "jangan"}

_WORD_RE = re.compile(r"[^\w\s-]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+", re.UNICODE)


@dataclass
class SentimentResult:
    label: str
    score: float
    positive_hits: list[str]
    negative_hits: list[str]

    @property
    def keywords(self) -> list[str]:
        combined = Counter()
        for term in self.positive_hits:
            combined[term] += 1
        for term in self.negative_hits:
            combined[term] += 1
        return [term for term, _ in combined.most_common(6)]


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = _WORD_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _is_negated(words: list[str], index: int) -> bool:
    window = words[max(0, index - 3) : index]
    return any(word in NEGATIONS for word in window)


def _count_terms(
    text: str, terms: dict[str, int]
) -> tuple[list[str], float]:
    """Kembalikan frasa yang cocok dan total bobotnya."""
    normalized = _normalize(text)
    if not normalized:
        return [], 0.0
    words = normalized.split()
    hits: list[str] = []
    total = 0.0
    for term, weight in terms.items():
        # Frasa multi-kata dicocokkan dengan substring yang dibatasi spasi.
        pattern = r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)"
        for match in re.finditer(pattern, normalized):
            prefix = normalized[: match.start()].split()
            if _is_negated(prefix, len(prefix)):
                # "tidak korupsi" bukan sentimen negatif; "tidak peduli" sudah
                # terdaftar sebagai frasa negatif sehingga tidak perlu dibalik.
                if term not in {"tidak peduli", "tidak hadir", "tidak transparan", "tidak akuntabel"}:
                    continue
            hits.append(term)
            total += weight
    return hits, total


def analyze_sentiment(title: str, content: str = "") -> SentimentResult:
    """Hitung sentimen dari judul (bobot 2x) dan isi berita."""
    title_hits_pos, title_pos = _count_terms(title, POSITIVE_TERMS)
    title_hits_neg, title_neg = _count_terms(title, NEGATIVE_TERMS)
    body_hits_pos, body_pos = _count_terms(content, POSITIVE_TERMS)
    body_hits_neg, body_neg = _count_terms(content, NEGATIVE_TERMS)

    positive = title_pos * 2 + body_pos
    negative = title_neg * 2 + body_neg
    total = positive + negative
    if total == 0:
        score = 0.0
    else:
        score = (positive - negative) / max(3.0, total)
    score = max(-1.0, min(1.0, round(score, 4)))

    if score >= 0.12:
        label = "positif"
    elif score <= -0.12:
        label = "negatif"
    else:
        label = "netral"

    positive_hits = list(dict.fromkeys(title_hits_pos + body_hits_pos))
    negative_hits = list(dict.fromkeys(title_hits_neg + body_hits_neg))
    return SentimentResult(
        label=label,
        score=score,
        positive_hits=positive_hits,
        negative_hits=negative_hits,
    )


def label_from_score(score: float) -> str:
    if score >= 0.12:
        return "positif"
    if score <= -0.12:
        return "negatif"
    return "netral"


def sentiment_label_id(label: str) -> str:
    return {"positif": "Positif", "negatif": "Negatif"}.get(label, "Netral")
