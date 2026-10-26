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
    ROLES,
    SENTIMENT_ROLES,
    STATUS_LABELS,
    STATUSES,
)
from .deps import consume_flashes
from .security import new_csrf_token
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
        "key": "activities",
        "label": "Kegiatan",
        "icon": "calendar",
        "href": "/kegiatan",
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
        ("activities", "/kegiatan"),
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
