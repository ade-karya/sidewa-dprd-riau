"""Enkripsi kunci API pihak ketiga yang disimpan per pengguna.

Kunci Gemini milik masing-masing pengguna tidak boleh tersimpan sebagai teks
biasa. Modul ini memakai konstruksi *encrypt-then-MAC* sederhana berbasis
HMAC-SHA256 dengan kunci turunan dari ``SIDEWA_SECRET_KEY``. Tidak ada
dependensi tambahan sehingga aman dipakai di lingkungan tanpa pustaka kripto
eksternal.

Format token: ``v1`` + nonce(16) + ciphertext + tag(16), lalu base64 URL-safe.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ..config import settings

_VERSION = b"v1"
_NONCE_BYTES = 16
_TAG_BYTES = 16
_MIN_SECRET_LENGTH = 16


class KeyVaultError(ValueError):
    """Kunci API tidak dapat dienkripsi atau didekripsi."""


def _master_key() -> bytes:
    secret = (settings.secret_key or "").encode("utf-8")
    if len(secret) < _MIN_SECRET_LENGTH:
        raise KeyVaultError(
            "SIDEWA_SECRET_KEY terlalu pendek untuk mengenkripsi kunci API."
        )
    return hashlib.sha256(b"sidewa-ai-key-vault:" + secret).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(
            hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return b"".join(chunks)[:length]


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    key = _master_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    plaintext = value.encode("utf-8")
    stream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(key, b"tag" + nonce + ciphertext, hashlib.sha256).digest()[
        :_TAG_BYTES
    ]
    return base64.urlsafe_b64encode(_VERSION + nonce + ciphertext + tag).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise KeyVaultError("Format kunci tersimpan tidak valid.") from exc
    if len(raw) < len(_VERSION) + _NONCE_BYTES + _TAG_BYTES or not raw.startswith(_VERSION):
        raise KeyVaultError("Format kunci tersimpan tidak valid.")
    nonce = raw[len(_VERSION) : len(_VERSION) + _NONCE_BYTES]
    tag = raw[-_TAG_BYTES:]
    ciphertext = raw[len(_VERSION) + _NONCE_BYTES : -_TAG_BYTES]
    key = _master_key()
    expected = hmac.new(key, b"tag" + nonce + ciphertext, hashlib.sha256).digest()[
        :_TAG_BYTES
    ]
    if not hmac.compare_digest(tag, expected):
        raise KeyVaultError(
            "Kunci API tidak dapat dibaca. Masukkan ulang kunci pada pengaturan."
        )
    stream = _keystream(key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream)).decode("utf-8")


def key_hint(value: str) -> str:
    """Petunjuk aman untuk ditampilkan di UI (tidak membocorkan kunci)."""
    cleaned = (value or "").strip()
    if len(cleaned) < 8:
        return "Kunci tersimpan"
    return f"••••••••{cleaned[-4:]}"
