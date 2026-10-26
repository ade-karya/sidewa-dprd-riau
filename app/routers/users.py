"""Manajemen pengguna dan hak akses."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import (
    ADMIN_ROLES,
    ROLE_LABELS,
    ROLE_STAF,
    ROLE_SUPERADMIN,
    ROLES,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles
from ..models import Commission, User
from ..security import (
    PasswordPolicyError,
    can_create_role,
    generate_password,
    hash_password,
    validate_password_strength,
)
from ..services.search import Page, paginate
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

ADMIN = require_roles(*ADMIN_ROLES)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _commissions(db: Session) -> list[Commission]:
    return db.query(Commission).order_by(Commission.sort_order).all()


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
    return user


def _assert_target(actor: User, target: User) -> None:
    if target.role == ROLE_SUPERADMIN and actor.role != ROLE_SUPERADMIN:
        raise HTTPException(
            status_code=403, detail="Hanya Super Admin yang dapat mengelola Super Admin."
        )
    if target.id == actor.id and actor.role != ROLE_SUPERADMIN:
        pass


def _validate_role(actor: User, role: str) -> None:
    if not can_create_role(actor.role, role):
        raise HTTPException(
            status_code=403, detail="Anda tidak berwenang memberikan peran tersebut."
        )


@router.get("/pengguna")
def list_users(
    request: Request,
    q: str = "",
    role: str = "",
    status: str = "active",
    page: int = 1,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(like),
                User.full_name.ilike(like),
                User.email.ilike(like),
            )
        )
    if role in ROLES:
        query = query.filter(User.role == role)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    query = query.order_by(User.is_active.desc(), User.full_name)
    result: Page = paginate(query, page, 15)
    return render(
        request,
        "users/list.html",
        user=user,
        result=result,
        commissions=_commissions(db),
        q=q,
        role=role,
        status=status,
        role_labels=ROLE_LABELS,
        active_count=db.query(User).filter(User.is_active.is_(True)).count(),
        total_count=db.query(User).count(),
    )


@router.get("/pengguna/baru")
def new_user(
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    allowed_roles = [r for r in ROLES if can_create_role(user.role, r)]
    return render(
        request,
        "users/form.html",
        user=user,
        target=None,
        commissions=_commissions(db),
        allowed_roles=allowed_roles,
        form={
            "username": "",
            "full_name": "",
            "email": "",
            "role": ROLE_STAF,
            "commission_code": "",
        },
        mode="create",
    )


@router.post("/pengguna")
async def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    role: str = Form(ROLE_STAF),
    commission_code: str = Form(""),
    password: str = Form(...),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    form = {
        "username": username,
        "full_name": full_name,
        "email": email,
        "role": role,
        "commission_code": commission_code,
    }
    allowed_roles = [r for r in ROLES if can_create_role(user.role, r)]
    error = None
    username = username.strip().lower()
    if not re.match(r"^[a-z0-9._-]{3,32}$", username):
        error = "Username 3–32 karakter, hanya huruf kecil, angka, titik, garis bawah, atau strip."
    elif db.query(User).filter(User.username == username).first():
        error = "Username sudah digunakan."
    if not error and len(full_name.strip()) < 3:
        error = "Nama lengkap minimal 3 karakter."
    if not error and email and not _EMAIL_RE.match(email.strip()):
        error = "Format email tidak valid."
    if not error and role not in allowed_roles:
        error = "Peran tidak diizinkan untuk akun Anda."
    commission = None
    if commission_code:
        commission = db.query(Commission).filter(Commission.code == commission_code).first()
    if not error and role == ROLE_STAF and not commission:
        error = "Staf Komisi wajib ditautkan ke salah satu komisi."
    if not error:
        try:
            validate_password_strength(password)
        except PasswordPolicyError as exc:
            error = str(exc)
    if error:
        return render(
            request,
            "users/form.html",
            user=user,
            status_code=400,
            target=None,
            commissions=_commissions(db),
            allowed_roles=allowed_roles,
            form=form,
            mode="create",
            error=error,
        )
    target = User(
        username=username,
        full_name=full_name.strip()[:160],
        email=email.strip().lower() or None,
        role=role,
        commission_id=commission.id if commission else None,
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=True,
    )
    db.add(target)
    audit(
        db,
        request,
        "USER_CREATE",
        actor=user,
        entity_type="user",
        summary=f"Membuat pengguna {target.username} dengan peran {ROLE_LABELS.get(role, role)}",
    )
    db.commit()
    flash(request, f"Pengguna {target.username} berhasil dibuat.", "success")
    return RedirectResponse("/pengguna", status_code=303)


@router.get("/pengguna/{user_id}/edit")
def edit_user(
    user_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    target = _user_or_404(db, user_id)
    _assert_target(user, target)
    allowed_roles = [r for r in ROLES if can_create_role(user.role, r)]
    if target.role not in allowed_roles:
        allowed_roles.append(target.role)
    return render(
        request,
        "users/form.html",
        user=user,
        target=target,
        commissions=_commissions(db),
        allowed_roles=allowed_roles,
        form={
            "username": target.username,
            "full_name": target.full_name,
            "email": target.email or "",
            "role": target.role,
            "commission_code": target.commission.code if target.commission else "",
        },
        mode="edit",
    )


@router.post("/pengguna/{user_id}/edit")
async def update_user(
    user_id: int,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(""),
    role: str = Form(...),
    commission_code: str = Form(""),
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    target = _user_or_404(db, user_id)
    _assert_target(user, target)
    allowed_roles = [r for r in ROLES if can_create_role(user.role, r)]
    if target.role not in allowed_roles:
        allowed_roles.append(target.role)
    form = {
        "username": target.username,
        "full_name": full_name,
        "email": email,
        "role": role,
        "commission_code": commission_code,
    }
    error = None
    if len(full_name.strip()) < 3:
        error = "Nama lengkap minimal 3 karakter."
    elif email and not _EMAIL_RE.match(email.strip()):
        error = "Format email tidak valid."
    elif role not in allowed_roles:
        error = "Peran tidak diizinkan."
    commission = None
    if commission_code:
        commission = db.query(Commission).filter(Commission.code == commission_code).first()
    if not error and role == ROLE_STAF and not commission:
        error = "Staf Komisi wajib ditautkan ke salah satu komisi."
    if error:
        return render(
            request,
            "users/form.html",
            user=user,
            status_code=400,
            target=target,
            commissions=_commissions(db),
            allowed_roles=allowed_roles,
            form=form,
            mode="edit",
            error=error,
        )
    target.full_name = full_name.strip()[:160]
    target.email = email.strip().lower() or None
    target.role = role
    target.commission_id = commission.id if commission else None
    audit(
        db,
        request,
        "USER_UPDATE",
        actor=user,
        entity_type="user",
        entity_id=target.id,
        summary=f"Memperbarui pengguna {target.username}",
    )
    db.commit()
    flash(request, "Data pengguna diperbarui.", "success")
    return RedirectResponse("/pengguna", status_code=303)


@router.post("/pengguna/{user_id}/status")
def toggle_user(
    user_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    target = _user_or_404(db, user_id)
    _assert_target(user, target)
    if target.id == user.id:
        flash(request, "Anda tidak dapat menonaktifkan akun sendiri.", "danger")
        return RedirectResponse("/pengguna", status_code=303)
    if target.role == ROLE_SUPERADMIN and target.is_active:
        active_superadmins = (
            db.query(User).filter(User.role == ROLE_SUPERADMIN, User.is_active.is_(True)).count()
        )
        if active_superadmins <= 1:
            flash(request, "Minimal harus ada satu Super Admin aktif.", "danger")
            return RedirectResponse("/pengguna", status_code=303)
    target.is_active = not target.is_active
    audit(
        db,
        request,
        "USER_DEACTIVATE",
        actor=user,
        entity_type="user",
        entity_id=target.id,
        summary=(
            f"Mengaktifkan pengguna {target.username}"
            if target.is_active
            else f"Menonaktifkan pengguna {target.username}"
        ),
    )
    db.commit()
    flash(request, f"Pengguna {'diaktifkan' if target.is_active else 'dinonaktifkan'}.", "success")
    return RedirectResponse("/pengguna", status_code=303)


@router.post("/pengguna/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    target = _user_or_404(db, user_id)
    _assert_target(user, target)
    new_password = generate_password()
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    target.failed_attempts = 0
    target.locked_until = None
    audit(
        db,
        request,
        "USER_PASSWORD",
        actor=user,
        entity_type="user",
        entity_id=target.id,
        summary=f"Mereset kata sandi {target.username}",
    )
    db.commit()
    request.session["new_api_token"] = None
    flash(
        request,
        f"Kata sandi sementara untuk {target.username}: {new_password} — catat dan sampaikan secara aman.",
        "warning",
    )
    return RedirectResponse("/pengguna", status_code=303)
