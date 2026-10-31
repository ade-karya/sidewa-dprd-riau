"""Skill bersama untuk gaya penulisan rilis Humas.

Hanya ada **satu** skill rilis yang dipakai semua pengelola konten. Isinya
tidak disunting manual: setiap kali rilis diterbitkan, diarsipkan, atau
disunting, ringkasan gaya belajar ulang dari kumpulan rilis yang sedang terbit.
Dengan begitu panduan yang dipakai Gemini selalu mengikuti publikasi terbaru.

Pembelajaran dilakukan secara deterministik (statistik teks), tanpa panggilan
Gemini tambahan, sehingga murah, cepat, dan dapat diaudit.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..constants import STATUS_PUBLISHED
from ..models import PressRelease, ReleaseSkill, utcnow

logger = logging.getLogger("sidewa.release_skills")

SHARED_SKILL_KEY = "gaya-rilis-humas"
SHARED_SKILL_NAME = "Gaya Rilis Humas"
SHARED_SKILL_DESCRIPTION = (
    "Panduan gaya siaran pers Humas DPRD Provinsi Riau yang diperbarui otomatis "
    "dari rilis yang sedang terbit."
)
DEFAULT_INSTRUCTIONS = (
    "Gunakan kaidah 5W1H, bahasa Indonesia jurnalistik yang lugas, dan kutipan "
    "narasumber yang akurat. Utamakan fakta yang disebut dalam rekaman, hindari "
    "opini, spekulasi, dan gelar yang tidak jelas sumbernya."
)
DEFAULT_LEARNED = (
    "Belum ada rilis terbit sebagai contoh. Ikuti kaidah 5W1H dan gaya siaran "
    "pers resmi pemerintah daerah sampai rilis pertama diterbitkan."
)
CORPUS_LIMIT = 40
REFRESH_AFTER = timedelta(minutes=15)


def _published(db: Session, limit: int = CORPUS_LIMIT) -> list[PressRelease]:
    return (
        db.query(PressRelease)
        .filter(PressRelease.status == STATUS_PUBLISHED)
        .order_by(PressRelease.published_at.desc(), PressRelease.id.desc())
        .limit(limit)
        .all()
    )


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def _paragraph_count(body: str) -> int:
    chunks = [part.strip() for part in re.split(r"\n\s*\n", body or "")]
    return len([part for part in chunks if part])


def _has_quote(body: str) -> bool:
    return bool(re.search(r"[\"“”]", body or ""))


def _learning_text(rows: list[PressRelease]) -> str:
    """Susun ringkasan gaya dari rilis yang terbit saat ini."""
    if not rows:
        return DEFAULT_LEARNED

    titles = [r.title.strip() for r in rows if (r.title or "").strip()]
    summaries = [r.summary.strip() for r in rows if (r.summary or "").strip()]
    bodies = [r.body.strip() for r in rows if (r.body or "").strip()]
    if not titles or not bodies:
        return DEFAULT_LEARNED

    first_words = Counter(
        title.split()[0].strip(".,:;!?—-")
        for title in titles
        if title.split()
    )
    tags = Counter(
        tag.strip() for row in rows for tag in row.tag_list if tag.strip()
    )
    paragraph_counts = [_paragraph_count(body) for body in bodies]
    body_words = [len(body.split()) for body in bodies]
    opening_pekanbaru = sum(
        1
        for body in bodies
        if body.lstrip().upper().startswith(("PEKANBARU", "PEKAN BARU"))
    )
    quote_count = sum(1 for body in bodies if _has_quote(body))
    dates = [row.release_date for row in rows if row.release_date]

    lines = [
        f"Basis belajar: {len(rows)} rilis terbit terakhir"
        + (
            f" ({min(dates).isoformat()} s.d. {max(dates).isoformat()})."
            if dates
            else "."
        ),
        f"Judul: rata-rata {_average([len(title) for title in titles])} karakter; "
        "kata pembuka tersering: "
        + ", ".join(word for word, _ in first_words.most_common(4))
        + ".",
        f"Ringkasan: rata-rata {_average([len(text) for text in summaries])} karakter; "
        + (
            f"{sum(1 for text in summaries if text.count('.') <= 2)} dari {len(summaries)} "
            "memakai satu sampai dua kalimat teras berita."
            if summaries
            else "belum ada contoh ringkasan yang terisi."
        ),
        f"Isi: rata-rata {_average(body_words)} kata dan "
        f"{_average(paragraph_counts)} paragraf; "
        f"{quote_count} dari {len(bodies)} memuat kutipan narasumber.",
    ]
    if opening_pekanbaru:
        lines.append(
            f"Pembuka isi: {opening_pekanbaru} dari {len(bodies)} diawali "
            "lokasi peristiwa (mis. “PEKANBARU — ”)."
        )
    if tags:
        lines.append(
            "Tag tersering: "
            + ", ".join(f"{tag} ({count})" for tag, count in tags.most_common(8))
            + "."
        )
    lines.append("Contoh judul terbaru:")
    lines.extend(f"- {title}" for title in titles[:5])
    return "\n".join(lines)[:4000]


def get_shared_skill(db: Session, *, create: bool = True) -> ReleaseSkill | None:
    """Ambil satu-satunya skill rilis bersama; buat bila belum ada."""
    row = (
        db.query(ReleaseSkill)
        .filter(
            ReleaseSkill.key == SHARED_SKILL_KEY,
            ReleaseSkill.is_active.is_(True),
        )
        .first()
    )
    if row is not None or not create:
        return row

    row = ReleaseSkill(
        key=SHARED_SKILL_KEY,
        name=SHARED_SKILL_NAME,
        description=SHARED_SKILL_DESCRIPTION,
        instructions=DEFAULT_INSTRUCTIONS,
        learned_preferences=DEFAULT_LEARNED,
        is_shared=True,
        auto_update=True,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # Worker lain lebih dulu membuat baris yang sama.
        db.rollback()
        row = (
            db.query(ReleaseSkill)
            .filter(ReleaseSkill.key == SHARED_SKILL_KEY)
            .first()
        )
    return row


def refresh_shared_skill(db: Session, *, commit: bool = False) -> tuple[ReleaseSkill, bool]:
    """Perbarui skill dari rilis yang terbit saat ini.

    Mengembalikan ``(baris, berubah)``. ``auto_update`` pada baris dapat
    dimatikan administrator; dalam kondisi itu isi skill dibiarkan apa adanya.
    """
    row = get_shared_skill(db)
    if row is None:  # pragma: no cover - create=True seharusnya selalu berhasil
        raise RuntimeError("Skill rilis bersama tidak dapat disiapkan.")

    rows = _published(db)
    changed = False
    if row.auto_update:
        text = _learning_text(rows)
        if text != row.learned_preferences:
            row.learned_preferences = text
            changed = True
        if row.source_count != len(rows):
            row.source_count = len(rows)
            changed = True
        row.auto_updated_at = utcnow() if changed else row.auto_updated_at
    if commit:
        db.commit()
    return row, changed


def ensure_shared_skill(db: Session, *, commit: bool = True) -> ReleaseSkill:
    """Perbarui skill bila sudah kedaluwarsa atau jumlah rilis berubah."""
    row = get_shared_skill(db)
    assert row is not None
    total = (
        db.query(PressRelease)
        .filter(PressRelease.status == STATUS_PUBLISHED)
        .count()
    )
    stale = (
        row.auto_updated_at is None
        or utcnow() - row.auto_updated_at > REFRESH_AFTER
        or row.source_count != total
    )
    if row.auto_update and stale:
        row, _ = refresh_shared_skill(db, commit=commit)
    return row


def skill_payload(row: ReleaseSkill) -> dict[str, Any]:
    """Data siap tampil untuk kartu skill di halaman rilis."""
    return {
        "key": row.key,
        "name": row.name,
        "description": row.description,
        "instructions": row.instructions,
        "learned_preferences": row.learned_preferences,
        "source_count": row.source_count,
        "auto_update": row.auto_update,
        "auto_updated_at": row.auto_updated_at,
        "is_shared": row.is_shared,
    }


def published_examples(db: Session, limit: int = 6) -> list[PressRelease]:
    """Rilis terbit terbaru sebagai contoh nyata untuk halaman skill."""
    return _published(db, limit=limit)


def prompt_block(db: Session) -> str:
    """Teks skill untuk disisipkan ke prompt Gemini."""
    row, _ = refresh_shared_skill(db, commit=True)
    return (
        f"SKILL BERSAMA — {row.name} "
        f"(otomatis dari {row.source_count} rilis terbit)\n"
        f"{row.instructions}\n"
        "PELAJARAN DARI RILIS YANG SUDAH TERBIT:\n"
        f"{row.learned_preferences}"
    )
