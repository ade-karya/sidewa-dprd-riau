"""Kata sandi, token, CSRF, dan aturan peran."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .constants import ADMIN_ROLES, ALL_ROLES, CONTENT_MANAGER_ROLES, ROLE_SUPERADMIN

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)

PASSWORD_MIN_LENGTH = 10
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,128}$")


class PasswordPolicyError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(f"Kata sandi minimal {PASSWORD_MIN_LENGTH} karakter.")
    if not PASSWORD_PATTERN.match(password):
        raise PasswordPolicyError(
            "Kata sandi harus memuat huruf besar, huruf kecil, angka, dan simbol."
        )


def generate_password(length: int = 16) -> str:
    """Kata sandi acak yang memenuhi kebijakan."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if PASSWORD_PATTERN.match(candidate):
            return candidate


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected, provided)


def generate_api_token() -> tuple[str, str, str]:
    """Kembalikan (token mentah, prefix, hash). Token hanya ditampilkan sekali."""
    raw = "sdw_" + secrets.token_urlsafe(36)
    prefix = raw[:12]
    return raw, prefix, hash_api_token(raw)


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def can_manage_content(role: str) -> bool:
    return role in CONTENT_MANAGER_ROLES


def can_manage_users(role: str) -> bool:
    return role in ADMIN_ROLES


def can_view_audit(role: str) -> bool:
    return role in ADMIN_ROLES


def can_manage_members(role: str) -> bool:
    return role in CONTENT_MANAGER_ROLES


def can_create_role(actor_role: str, target_role: str) -> bool:
    if target_role not in ALL_ROLES:
        return False
    if actor_role == ROLE_SUPERADMIN:
        return True
    if actor_role in ADMIN_ROLES:
        return target_role != ROLE_SUPERADMIN
    return False


def lockout_deadline(now: datetime | None = None) -> datetime:
    base = now or datetime.utcnow()
    return base + timedelta(minutes=15)
