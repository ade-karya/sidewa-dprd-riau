"""Resolusi identitas anggota dewan untuk menyaring pemberitaan media online.

Tavily sering mengembalikan berita tentang orang lain yang namanya mirip, atau
anggota DPRD dari daerah lain. Modul ini menyusun "jangkar identitas" (nama,
variasi ejaan/gelar, instansi, lokasi, jabatan, partai, rentang tahun, akun
resmi) yang dipakai Gemini untuk memastikan berita memang tentang orang yang
benar.

Data tambahan per anggota bersifat opsional dan dibaca dari berkas JSON
``SIDEWA_MEMBER_IDENTITY_FILE`` (default ``data/member_identity.json``).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..models import Member

logger = logging.getLogger("sidewa.identity")

# Sapaan/honorifik yang lazim mendahului nama Indonesia.
_HONORIFICS = {
    "h",
    "hj",
    "dr",
    "drs",
    "dra",
    "ir",
    "prof",
    "kh",
    "ust",
    "ustadz",
    "ustadzah",
    "bc",
    "r",
    "rd",
    "ny",
    "nyi",
    "bpk",
    "bapak",
    "ibu",
}

# Gelar akademik/profesi yang lazim ditulis setelah nama.
_DEGREES = {
    "s",
    "m",
    "a",
    "se",
    "sh",
    "st",
    "ssos",
    "sos",
    "skom",
    "sked",
    "sip",
    "sap",
    "spt",
    "spsi",
    "shut",
    "shukum",
    "mm",
    "msi",
    "mh",
    "mpd",
    "ma",
    "mkn",
    "mkes",
    "mfarm",
    "mpsi",
    "mt",
    "mba",
    "mim",
    "phd",
    "ak",
    "ca",
    "cpa",
    "cma",
    "cpma",
    "qia",
    "cfe",
}

_WORD_RE = re.compile(r"[^\w\s,.'-]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+", re.UNICODE)

_CACHE: tuple[str, float, int, dict] | None = None


@dataclass
class MemberIdentity:
    """Jangkar identitas yang dikirim ke Gemini bersama setiap berita."""

    member_id: int
    full_name: str
    names: list[str] = field(default_factory=list)
    institution: str = ""
    location: str = ""
    position: str = ""
    party: str = ""
    commission: str = ""
    organizations: list[str] = field(default_factory=list)
    year_from: int = 0
    year_to: int = 0
    official_accounts: list[str] = field(default_factory=list)
    official_domains: list[str] = field(default_factory=list)
    photo_reference: str = ""
    notes: str = ""

    def year_valid(self, published_at: datetime | None) -> bool:
        """True bila tahun terbit berada dalam rentang yang relevan."""
        if published_at is None:
            return True
        if self.year_from and published_at.year < self.year_from:
            return False
        if self.year_to and published_at.year > self.year_to:
            return False
        return True

    def prompt_block(self) -> str:
        lines = [
            f"Nama resmi: {self.full_name}",
            f"Variasi ejaan/gelar yang sah: {', '.join(self.names) if self.names else '-'}",
            f"Jabatan/profesi: {self.position or '-'}",
            f"Instansi/lembaga: {self.institution or '-'}",
            f"Partai/organisasi: {', '.join(self.organizations) if self.organizations else '-'}",
            f"Komisi/bidang: {self.commission or '-'}",
            f"Lokasi/dapil: {self.location or '-'}",
            f"Rentang tahun relevan: {self.year_from or '-'}–{self.year_to or '-'}",
        ]
        if self.official_accounts:
            lines.append("Akun resmi: " + ", ".join(self.official_accounts[:8]))
        if self.official_domains:
            lines.append("Domain akun resmi: " + ", ".join(self.official_domains[:8]))
        if self.photo_reference:
            lines.append(
                "Foto resmi: tersedia pada profil anggota "
                f"({self.photo_reference}); jangan mengidentifikasi hanya dari nama."
            )
        if self.notes:
            lines.append(f"Catatan identitas: {self.notes}")
        return "\n".join(lines)


def _clean_name(value: str) -> str:
    text = _WORD_RE.sub(" ", value or "")
    text = _SPACE_RE.sub(" ", text)
    return text.strip(" ,-")


def _token_key(token: str) -> str:
    """Bentuk token tanpa titik untuk mencocokkan gelar/honorifik."""
    return token.lower().replace(".", "")


def _split_degrees(value: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def name_variants(full_name: str, aliases: list[str] | None = None) -> list[str]:
    """Buat variasi nama yang lazim muncul di media, tanpa gelar/honorifik."""
    original, degree_parts = _split_degrees(full_name)
    tokens = [token for token in _clean_name(original).split() if token]
    while tokens and _token_key(tokens[0].strip(",")) in _HONORIFICS:
        tokens.pop(0)
    # Buang gelar yang menempel di belakang nama tanpa koma.
    while len(tokens) > 1 and _token_key(tokens[-1].strip(",")) in _DEGREES:
        tokens.pop()
    primary = " ".join(tokens)

    candidates: list[str] = []
    cleaned_full = _clean_name(full_name)
    if cleaned_full:
        candidates.append(cleaned_full)
    if primary:
        candidates.append(primary)
    if len(tokens) >= 3:
        candidates.append(f"{tokens[0]} {tokens[-1]}")
        candidates.append(f"{tokens[0]} {tokens[1]} {tokens[-1]}")
    if len(tokens) >= 2:
        candidates.append(f"{tokens[0][0]}. {tokens[-1]}")
    if primary and degree_parts:
        degrees = " ".join(_clean_name(part) for part in degree_parts)
        if degrees:
            candidates.append(f"{primary} {degrees}")

    for alias in aliases or []:
        cleaned = _clean_name(alias)
        if cleaned:
            candidates.append(cleaned)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if len(candidate) < 3 or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
        if len(result) >= 10:
            break
    return result


def _official_domains(accounts: list[str]) -> list[str]:
    domains: list[str] = []
    for account in accounts:
        try:
            host = urllib.parse.urlparse(account).netloc.lower()
        except ValueError:
            continue
        if host.startswith("www."):
            host = host[4:]
        if host and host not in domains:
            domains.append(host)
    return domains


def _read_overrides() -> dict:
    global _CACHE
    path = Path(settings.member_identity_file)
    try:
        stat = path.stat()
    except OSError:
        return {}
    cache_key = str(path)
    if (
        _CACHE
        and _CACHE[0] == cache_key
        and _CACHE[1] == stat.st_mtime
        and _CACHE[2] == stat.st_size
    ):
        return _CACHE[3]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Berkas identitas anggota tidak valid: %s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("Berkas identitas anggota harus berupa objek JSON.")
        return {}
    raw = data.get("members", data)
    if not isinstance(raw, dict):
        return {}
    result = {
        str(key): value for key, value in raw.items() if isinstance(value, dict)
    }
    _CACHE = (cache_key, stat.st_mtime, stat.st_size, result)
    return result


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def resolve_identity(member: Member) -> MemberIdentity:
    """Gabungkan data anggota di database dengan overrides opsional.

    Memakai ``getattr`` agar aman dipakai pada objek ringan (mis. stub uji)
    yang tidak memuat seluruh atribut model.
    """
    member_id = getattr(member, "id", None)
    full_name = str(getattr(member, "full_name", "") or "")
    party = str(getattr(member, "party", "") or "")
    override = _read_overrides().get(str(member_id), {})
    aliases = override.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [str(alias) for alias in aliases if str(alias).strip()]

    organizations = override.get("organizations") or []
    if isinstance(organizations, str):
        organizations = [organizations]
    organizations = [str(item) for item in organizations if str(item).strip()]
    if not organizations and party:
        organizations = [party]

    accounts = override.get("official_accounts") or []
    if isinstance(accounts, str):
        accounts = [accounts]
    accounts = [str(item).strip() for item in accounts if str(item).strip()]

    commission = ""
    commission_obj = getattr(member, "commission", None)
    if commission_obj is not None:
        commission = f"Komisi {getattr(commission_obj, 'code', '')}"
        if getattr(commission_obj, "bidang", ""):
            commission += f" — {commission_obj.bidang}"

    year_from = _as_int(override.get("year_from"), settings.sentiment_year_from)
    year_to = _as_int(override.get("year_to"), settings.sentiment_year_to)
    if not year_to:
        year_to = datetime.now().year + 1

    portrait_path = getattr(member, "portrait_path", "") or ""
    photo = str(override.get("photo_url") or "").strip()
    if not photo and portrait_path:
        photo = f"/media/{portrait_path}"

    return MemberIdentity(
        member_id=member_id or 0,
        full_name=full_name,
        names=name_variants(full_name, aliases),
        institution=str(override.get("institution") or settings.organization),
        location=str(
            override.get("location")
            or getattr(member, "dapil", "")
            or settings.sentiment_location
            or "Provinsi Riau"
        ),
        position=str(override.get("position") or getattr(member, "position", "") or ""),
        party=party,
        commission=commission,
        organizations=organizations,
        year_from=year_from,
        year_to=year_to,
        official_accounts=accounts,
        official_domains=_official_domains(accounts),
        photo_reference=photo,
        notes=str(override.get("notes") or ""),
    )


def article_has_out_of_region_hint(title: str, snippet: str, identity: MemberIdentity) -> bool:
    """Deteksi kasar berita yang jelas membahas DPRD/daerah lain tanpa Riau.

    Dipakai hanya saat Gemini tidak tersedia. Tujuannya menahan kasus nama sama
    di provinsi/kabupaten lain, bukan menggantikan penilaian Gemini.
    """
    text = f"{title} {snippet}".lower()
    if "riau" in text:
        return False
    other_regions = (
        "jawa barat",
        "jawa tengah",
        "jawa timur",
        "sumatera utara",
        "sumatera selatan",
        "sumatera barat",
        "kalimantan",
        "sulawesi",
        "papua",
        "bali",
        "ntb",
        "ntt",
        "maluku",
        "banten",
        "dki jakarta",
        "yogyakarta",
        "lampung",
        "aceh",
        "jambi",
        "bengkulu",
        "kepulauan riau",
        "bangka belitung",
    )
    if any(region in text for region in other_regions):
        return True
    if "dpr ri" in text and "dprd" not in text:
        return True
    return False
