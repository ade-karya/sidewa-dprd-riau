"""Konfigurasi aplikasi berbasis environment variable."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Pembaca .env minimal tanpa dependensi tambahan."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ya", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    app_name: str = "SIDEWA"
    app_long_name: str = "Sistem Dokumentasi Kegiatan Dewan"
    organization: str = "DPRD Provinsi Riau"
    app_env: str = field(default_factory=lambda: os.getenv("SIDEWA_ENV", "development"))
    debug: bool = field(default_factory=lambda: _bool("SIDEWA_DEBUG", False))
    secret_key: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_SECRET_KEY", "dev-secret-ganti-di-produksi-" + secrets.token_hex(8)
        )
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("SIDEWA_BASE_URL", "http://localhost:8000")
    )
    timezone: str = field(default_factory=lambda: os.getenv("SIDEWA_TIMEZONE", "Asia/Jakarta"))

    database_url: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'sidewa.db'}"
        )
    )
    media_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("SIDEWA_MEDIA_ROOT", str(BASE_DIR / "data" / "media"))
        )
    )
    max_upload_mb: int = field(default_factory=lambda: _int("SIDEWA_MAX_UPLOAD_MB", 15))
    max_photos_per_activity: int = field(default_factory=lambda: _int("SIDEWA_MAX_PHOTOS", 12))
    max_image_pixels: int = field(
        default_factory=lambda: _int("SIDEWA_MAX_IMAGE_PIXELS", 40_000_000)
    )
    session_max_age: int = field(default_factory=lambda: _int("SIDEWA_SESSION_MAX_AGE", 8 * 3600))
    cookie_secure: bool = field(
        default_factory=lambda: _bool(
            "SIDEWA_COOKIE_SECURE", os.getenv("SIDEWA_ENV", "development") == "production"
        )
    )

    face_detector: str = field(default_factory=lambda: os.getenv("SIDEWA_FACE_DETECTOR", "hog"))
    face_upsample: int = field(default_factory=lambda: _int("SIDEWA_FACE_UPSAMPLE", 1))
    face_tolerance: float = field(default_factory=lambda: _float("SIDEWA_FACE_TOLERANCE", 0.60))
    face_auto_tag: float = field(default_factory=lambda: _float("SIDEWA_FACE_AUTO_TAG", 0.45))
    face_review: float = field(default_factory=lambda: _float("SIDEWA_FACE_REVIEW", 0.58))
    face_match_margin: float = field(
        default_factory=lambda: _float("SIDEWA_FACE_MATCH_MARGIN", 0.08)
    )
    face_sync: bool = field(default_factory=lambda: _bool("SIDEWA_FACE_SYNC", False))
    face_workers: int = field(default_factory=lambda: _int("SIDEWA_FACE_WORKERS", 2))
    face_max_dimension: int = field(default_factory=lambda: _int("SIDEWA_FACE_MAX_DIM", 1400))

    demo_mode: bool = field(default_factory=lambda: _bool("SIDEWA_DEMO_MODE", True))
    bootstrap_admin_username: str = field(
        default_factory=lambda: os.getenv("SIDEWA_BOOTSTRAP_ADMIN_USERNAME", "")
    )
    bootstrap_admin_password: str = field(
        default_factory=lambda: os.getenv("SIDEWA_BOOTSTRAP_ADMIN_PASSWORD", "")
    )
    bootstrap_admin_name: str = field(
        default_factory=lambda: os.getenv("SIDEWA_BOOTSTRAP_ADMIN_NAME", "Administrator SIDEWA")
    )

    trusted_hosts: list[str] = field(default_factory=lambda: _list("SIDEWA_TRUSTED_HOSTS"))
    cors_origins: list[str] = field(default_factory=lambda: _list("SIDEWA_CORS_ORIGINS"))
    log_level: str = field(default_factory=lambda: os.getenv("SIDEWA_LOG_LEVEL", "INFO"))
    metrics_token: str = field(default_factory=lambda: os.getenv("SIDEWA_METRICS_TOKEN", ""))

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        return self.max_upload_bytes * self.max_photos_per_activity + 2 * 1024 * 1024

    def ensure_dirs(self) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        (self.media_root / "activities").mkdir(exist_ok=True)
        (self.media_root / "members").mkdir(exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", "", 1))
            if not db_path.is_absolute():
                db_path = BASE_DIR / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
