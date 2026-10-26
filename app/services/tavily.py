"""Klien Tavily untuk pencarian pemberitaan media online.

Tavily dipakai oleh admin komisi untuk memindai pemberitaan tentang anggota
dewan. Hasil pencarian dinormalisasi, lalu disimpan sebagai ``MediaMention``
dan dianalisis sentimennya secara lokal.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from ..config import settings
from ..models import Member

logger = logging.getLogger("sidewa.tavily")


class TavilyError(RuntimeError):
    pass


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def build_query(member: Member) -> str:
    """Susun kueri yang relevan dengan tugas dan fungsi dewan."""
    parts = [f'"{member.full_name}"', "DPRD", "Riau"]
    if member.commission and member.commission.bidang:
        bidang = member.commission.bidang.split(",")[0].strip()
        if bidang:
            parts.append(bidang)
    return " ".join(parts)


def search_news(
    query: str,
    *,
    max_results: int | None = None,
    days: int | None = None,
    search_depth: str | None = None,
) -> list[dict]:
    """Panggil Tavily Search API dan kembalikan hasil yang sudah dinormalisasi."""
    if not settings.tavily_configured:
        raise TavilyError(
            "Tavily belum dikonfigurasi. Isi SIDEWA_TAVILY_API_KEY pada berkas .env."
        )

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": search_depth or settings.tavily_search_depth,
        "topic": "news",
        "max_results": max(1, min(20, max_results or settings.tavily_max_results)),
        "days": max(1, days or settings.tavily_days),
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    request = urllib.request.Request(
        settings.tavily_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SIDEWA-DPRD-Riau/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        logger.warning("Tavily HTTP %s: %s", exc.code, detail)
        raise TavilyError(
            f"Tavily menolak permintaan (HTTP {exc.code}). Periksa API key dan kuota."
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Tavily tidak dapat dihubungi: %s", exc)
        raise TavilyError("Tavily tidak dapat dihubungi. Coba lagi beberapa saat.") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TavilyError("Respons Tavily tidak valid.") from exc

    if not isinstance(data, dict):
        raise TavilyError("Respons Tavily tidak valid.")
    if data.get("error"):
        raise TavilyError(str(data["error"])[:300])

    results = data.get("results") or []
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = (item.get("title") or "").strip()
        content = (item.get("content") or item.get("raw_content") or "").strip()
        if not title and not content:
            continue
        normalized.append(
            {
                "title": title[:400],
                "url": url,
                "source": _domain(url) or "Media online",
                "snippet": content[:2000],
                "published_at": _parse_published(
                    item.get("published_date") or item.get("published_at")
                ),
                "relevance": item.get("score"),
            }
        )
    return normalized
