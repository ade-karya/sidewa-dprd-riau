"""Helper format tanggal, angka, dan teks khas Indonesia."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import settings

MONTHS_ID = [
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]

MONTHS_SHORT_ID = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "Mei",
    "Jun",
    "Jul",
    "Agu",
    "Sep",
    "Okt",
    "Nov",
    "Des",
]

DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

LOCAL_TZ = ZoneInfo(settings.timezone)


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ)


def format_date_id(value: date | datetime | None, with_day: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = to_local(value).date()
    text = f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}"
    if with_day:
        text = f"{DAYS_ID[value.weekday()]}, {text}"
    return text


def format_date_short_id(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = to_local(value).date()
    return f"{value.day:02d} {MONTHS_SHORT_ID[value.month - 1]} {value.year}"


def format_datetime_id(value: datetime | None, with_zone: bool = True) -> str:
    if value is None:
        return "—"
    local = to_local(value)
    suffix = " WIB" if with_zone else ""
    return f"{local.day} {MONTHS_SHORT_ID[local.month - 1]} {local.year}, {local:%H.%M}{suffix}"


def time_ago(value: datetime | None) -> str:
    if value is None:
        return "—"
    local = to_local(value).replace(tzinfo=None)
    now = local_now().replace(tzinfo=None)
    delta = now - local
    seconds = int(delta.total_seconds())
    if seconds < 45:
        return "baru saja"
    if seconds < 3600:
        return f"{seconds // 60} menit lalu"
    if seconds < 86400:
        return f"{seconds // 3600} jam lalu"
    if seconds < 86400 * 30:
        return f"{seconds // 86400} hari lalu"
    return format_date_short_id(local)


def human_filesize(size: int | None) -> str:
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = min(int(math.log(size, 1024)), len(units) - 1)
    value = size / (1024**index)
    return f"{value:.1f} {units[index]}".replace(".0 ", " ")


def time_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start}–{end} WIB"
    if start:
        return f"{start} WIB"
    return ""


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def mask_token(token: str) -> str:
    if len(token) <= 12:
        return token
    return f"{token[:8]}••••••••{token[-4:]}"


def utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def date_range_last_months(months: int = 6) -> list[tuple[int, int]]:
    today = local_now().date().replace(day=1)
    result: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(months):
        result.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(result))


def month_label(year: int, month: int) -> str:
    return f"{MONTHS_SHORT_ID[month - 1]} {str(year)[2:]}"


def previous_period(days: int = 30) -> tuple[datetime, datetime]:
    end = utc_naive_now()
    return end - timedelta(days=days), end
