"""Autentikasi, profil, dan token API."""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import ROLE_LABELS
from ..database import get_db
from ..deps import csrf_protect, flash, get_current_user, require_user
from ..models import ApiToken, AuditLog, User, utcnow
from ..security import (
    PasswordPolicyError,
    generate_api_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _demo_accounts() -> list[dict]:
    if not settings.demo_mode:
        return []
    from ..services.seed import demo_credentials

    return demo_credentials()


def _safe_next(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return "/"
    if value.startswith("/login"):
        return "/"
    return value


@router.get("/login")
def login_page(request: Request, next: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return render(
        request,
        "auth/login.html",
        user=None,
        next_path=_safe_next(next),
        demo_accounts=_demo_accounts(),
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    error = None
    if user is None:
        # Tetap jalankan verifikasi dummy agar waktu respons seragam.
        verify_password(
            password,
            "$argon2id$v=19$m=65536,t=3,p=2$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        error = "Nama pengguna atau kata sandi salah."
    elif not user.is_active:
        error = "Akun dinonaktifkan. Hubungi administrator."
    elif user.locked_until and user.locked_until > utcnow():
        minutes = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        error = f"Akun terkunci sementara. Coba lagi dalam {minutes} menit."
    elif not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = utcnow() + timedelta(minutes=15)
            user.failed_attempts = 0
        audit(
            db,
            request,
            "LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
            summary=f"Gagal masuk untuk akun {user.username}",
            actor=user,
        )
        db.commit()
        error = "Nama pengguna atau kata sandi salah."

    if error:
        return render(
            request,
            "auth/login.html",
            user=None,
            status_code=401,
            error=error,
            username=username,
            next_path=_safe_next(next),
            demo_accounts=_demo_accounts(),
        )

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit(
        db,
        request,
        "LOGIN",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} masuk ke aplikasi",
        actor=user,
    )
    db.commit()

    request.session.clear()
    request.session["user_id"] = user.id
    from ..security import new_csrf_token

    request.session["csrf"] = new_csrf_token()
    flash(request, f"Selamat datang, {user.full_name}.", "success")
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    audit(
        db,
        request,
        "LOGOUT",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} keluar dari aplikasi",
    )
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/profil")
def profile(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    tokens = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    my_audit = (
        db.query(AuditLog)
        .filter(AuditLog.actor_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )
    return render(
        request,
        "auth/profile.html",
        user=user,
        tokens=tokens,
        my_audit=my_audit,
        role_label=ROLE_LABELS.get(user.role, user.role),
    )


@router.post("/profil")
def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    full_name = full_name.strip()
    email = email.strip().lower()
    if len(full_name) < 3:
        flash(request, "Nama lengkap minimal 3 karakter.", "danger")
        return RedirectResponse("/profil", status_code=303)
    if email and not _EMAIL_RE.match(email):
        flash(request, "Format email tidak valid.", "danger")
        return RedirectResponse("/profil", status_code=303)
    user.full_name = full_name
    user.email = email or None
    audit(
        db,
        request,
        "USER_UPDATE",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Memperbarui profil sendiri",
    )
    db.commit()
    flash(request, "Profil berhasil diperbarui.", "success")
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not verify_password(current_password, user.password_hash):
        flash(request, "Kata sandi saat ini tidak sesuai.", "danger")
        return RedirectResponse("/profil", status_code=303)
    if new_password != confirm_password:
        flash(request, "Konfirmasi kata sandi baru tidak sama.", "danger")
        return RedirectResponse("/profil", status_code=303)
    try:
        validate_password_strength(new_password)
    except PasswordPolicyError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/profil", status_code=303)
    if verify_password(new_password, user.password_hash):
        flash(request, "Kata sandi baru harus berbeda dari kata sandi lama.", "danger")
        return RedirectResponse("/profil", status_code=303)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    audit(
        db,
        request,
        "USER_PASSWORD",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Mengubah kata sandi sendiri",
    )
    db.commit()
    flash(request, "Kata sandi berhasil diubah.", "success")
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/token")
def create_token(
    request: Request,
    name: str = Form("Token integrasi"),
    days: int = Form(0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raw, prefix, token_hash = generate_api_token()
    expires = utcnow() + timedelta(days=days) if days > 0 else None
    token = ApiToken(
        user_id=user.id,
        name=name.strip()[:120] or "Token integrasi",
        prefix=prefix,
        token_hash=token_hash,
        expires_at=expires,
    )
    db.add(token)
    audit(
        db,
        request,
        "TOKEN_CREATE",
        actor=user,
        entity_type="api_token",
        summary=f"Membuat token API '{token.name}'",
    )
    db.commit()
    request.session["new_api_token"] = raw
    flash(
        request,
        "Token API berhasil dibuat. Salin sekarang — token tidak ditampilkan lagi.",
        "warning",
    )
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/token/{token_id}/hapus")
def revoke_token(
    token_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    token = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.user_id == user.id).first()
    if not token:
        flash(request, "Token tidak ditemukan.", "danger")
        return RedirectResponse("/profil", status_code=303)
    token.is_active = False
    audit(
        db,
        request,
        "TOKEN_REVOKE",
        actor=user,
        entity_type="api_token",
        entity_id=token.id,
        summary=f"Mencabut token API '{token.name}'",
    )
    db.commit()
    flash(request, "Token API dicabut.", "success")
    return RedirectResponse("/profil", status_code=303)
