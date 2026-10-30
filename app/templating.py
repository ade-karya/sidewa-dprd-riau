"""Konfigurasi Jinja2, konteks global, dan helper render."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates

from . import __version__
from .config import settings
from .constants import (
    ADMIN_ROLES,
    AUDIT_ROLES,
    CATEGORIES,
    CATEGORY_TONES,
    CONTENT_MANAGER_ROLES,
    PHOTO_STATUS_LABELS,
    ROLE_ANGGOTA,
    ROLE_DESCRIPTIONS,
    ROLE_LABELS,
    ROLE_STAF_HUMAS,
    ROLES,
    SENTIMENT_ROLES,
    STAFF_VIEW_ROLES,
    STATUS_LABELS,
    STATUSES,
    SELECTION_STATUS_LABELS,
    SELECTION_STATUS_TONES,
    SELECTION_VERDICT_LABELS,
    SELECTION_VERDICT_TONES,
)
from .deps import consume_flashes
from .security import new_csrf_token
from .services.images import full_path as media_full
from .services.images import thumb_path as media_thumb
from .utils import (
    format_date_id,
    format_date_short_id,
    format_datetime_id,
    human_filesize,
    initials,
    time_ago,
    time_range,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

templates.env.filters.update(
    {
        "date_id": format_date_id,
        "date_short": format_date_short_id,
        "datetime_id": format_datetime_id,
        "time_ago": time_ago,
        "filesize": human_filesize,
        "initials": initials,
        "time_range": time_range,
        "media_full": media_full,
        "media_thumb": media_thumb,
    }
)


def page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    return f"{request.url.path}?{urlencode(params)}"


templates.env.globals.update(
    {
        "page_url": page_url,
        "app_name": settings.app_name,
        "app_long_name": settings.app_long_name,
        "organization": settings.organization,
        "app_version": __version__,
        "demo_mode": settings.demo_mode,
        "role_labels": ROLE_LABELS,
        "role_descriptions": ROLE_DESCRIPTIONS,
        "roles": ROLES,
        "status_labels": STATUS_LABELS,
        "statuses": STATUSES,
        "photo_status_labels": PHOTO_STATUS_LABELS,
        "categories": CATEGORIES,
        "category_tones": CATEGORY_TONES,
        "selection_status_labels": SELECTION_STATUS_LABELS,
        "selection_status_tones": SELECTION_STATUS_TONES,
        "selection_verdict_labels": SELECTION_VERDICT_LABELS,
        "selection_verdict_tones": SELECTION_VERDICT_TONES,
    }
)


NAV_ITEMS = [
    {"key": "dashboard", "label": "Beranda", "icon": "home", "href": "/", "roles": None},
    {
        "key": "member_dashboard",
        "label": "Dashboard Saya",
        "icon": "user",
        "href": "/dashboard-anggota",
        "roles": {ROLE_ANGGOTA},
    },
    {
        "key": "staff_dashboard",
        "label": "Ruang Kerja",
        "icon": "presentation",
        "href": "/dashboard-staf",
        "roles": {ROLE_STAF_HUMAS},
    },
    {
        "key": "humas_staff",
        "label": "Staf Humas",
        "icon": "book-open",
        "href": "/staf-humas",
        "roles": STAFF_VIEW_ROLES,
    },
    {
        "key": "photo_selection",
        "label": "Seleksi Foto",
        "icon": "sparkles",
        "href": "/seleksi-foto",
        "roles": CONTENT_MANAGER_ROLES,
    },
    {
        "key": "activities",
        "label": "Kegiatan",
        "icon": "calendar",
        "href": "/kegiatan",
        "roles": None,
    },
    {
        "key": "releases",
        "label": "Rilis",
        "icon": "send",
        "href": "/rilis",
        "roles": None,
    },
    {"key": "search", "label": "Cari Wajah", "icon": "scan", "href": "/cari", "roles": None},
    {"key": "members", "label": "Anggota", "icon": "users", "href": "/anggota", "roles": None},
    {"key": "commissions", "label": "Komisi", "icon": "layers", "href": "/komisi", "roles": None},
    {
        "key": "sentiment",
        "label": "Sentimen",
        "icon": "chart",
        "href": "/sentimen",
        "roles": SENTIMENT_ROLES,
    },
    {
        "key": "users",
        "label": "Pengguna",
        "icon": "shield",
        "href": "/pengguna",
        "roles": ADMIN_ROLES,
    },
    {"key": "audit", "label": "Audit", "icon": "activity", "href": "/audit", "roles": AUDIT_ROLES},
]


def visible_nav(user) -> list[dict]:
    if user is None:
        return []
    items = []
    for item in NAV_ITEMS:
        if item["roles"] is None or user.role in item["roles"]:
            items.append(item)
    return items


def _active_key(path: str) -> str:
    if path == "/":
        return "dashboard"
    for key, prefix in (
        ("member_dashboard", "/dashboard-anggota"),
        ("staff_dashboard", "/dashboard-staf"),
        ("humas_staff", "/staf-humas"),
        ("photo_selection", "/seleksi-foto"),
        ("activities", "/kegiatan"),
        ("releases", "/rilis"),
        ("search", "/cari"),
        ("members", "/anggota"),
        ("commissions", "/komisi"),
        ("sentiment", "/sentimen"),
        ("users", "/pengguna"),
        ("audit", "/audit"),
    ):
        if path.startswith(prefix):
            return key
    if path.startswith("/profil"):
        return "profile"
    return ""


def render(request: Request, name: str, *, user=None, status_code: int = 200, **context):
    if user is None:
        user = getattr(request.state, "user", None)
    csrf = request.session.get("csrf")
    if not csrf:
        csrf = new_csrf_token()
        request.session["csrf"] = csrf
    new_token = request.session.pop("new_api_token", None)
    context.update(
        {
            "request": request,
            "user": user,
            "csrf_token": csrf,
            "nav_items": visible_nav(user),
            "active_nav": _active_key(request.url.path),
            "flashes": consume_flashes(request),
            "new_api_token": new_token,
            "settings": settings,
            "can_manage_content": bool(user and user.role in CONTENT_MANAGER_ROLES),
            "can_manage_users": bool(user and user.role in ADMIN_ROLES),
            "can_view_audit": bool(user and user.role in AUDIT_ROLES),
            "current_path": request.url.path,
        }
    )
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )
