"""Dependensi FastAPI: autentikasi, otorisasi, CSRF, dan flash message."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .constants import ALL_ROLES, ROLE_LABELS
from .database import get_db
from .models import ApiToken, User, utcnow
from .security import csrf_tokens_match, hash_api_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def flash(request: Request, message: str, category: str = "success") -> None:
    items = request.session.setdefault("_flashes", [])
    items.append({"message": message, "category": category})
    request.session["_flashes"] = items[-8:]


def consume_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        return None
    request.state.user = user
    return user


def require_user(request: Request, user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?next={quote(next_path, safe='/')}"},
        )
    return user


def require_roles(*roles: str):
    allowed = set(roles) & ALL_ROLES
    if not allowed:
        raise ValueError("Daftar peran tidak valid")

    def dependency(user: User = Depends(require_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki izin untuk mengakses halaman ini.",
            )
        return user

    return dependency


def require_superadmin(user: User = Depends(require_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Hanya Super Admin yang dapat mengakses.")
    return user


async def csrf_protect(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return
    expected = request.session.get("csrf")
    provided = request.headers.get("x-csrf-token")
    if not provided:
        content_type = request.headers.get("content-type", "")
        if "form" in content_type:
            form = await request.form()
            value = form.get("csrf_token")
            provided = value if isinstance(value, str) else None
    if not csrf_tokens_match(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sesi kedaluwarsa atau token keamanan tidak valid. Muat ulang halaman.",
        )


async def api_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Autentikasi API melalui Bearer token atau sesi (dengan CSRF untuk write)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth.split(" ", 1)[1].strip()
        token = (
            db.query(ApiToken)
            .filter(ApiToken.token_hash == hash_api_token(raw), ApiToken.is_active.is_(True))
            .first()
        )
        if not token or (token.expires_at and token.expires_at < utcnow()):
            raise HTTPException(
                status_code=401,
                detail="Token API tidak valid atau telah kedaluwarsa.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not token.user or not token.user.is_active:
            raise HTTPException(status_code=401, detail="Pemilik token tidak aktif.")
        token.last_used_at = utcnow()
        db.commit()
        return token.user

    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Autentikasi diperlukan. Gunakan sesi atau Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if request.method not in SAFE_METHODS:
        await csrf_protect(request)
    return user


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)
