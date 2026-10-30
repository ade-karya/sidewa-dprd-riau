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
    face_login_tolerance: float = field(
        default_factory=lambda: _float("SIDEWA_FACE_LOGIN_TOLERANCE", 0.50)
    )
    face_login_margin: float = field(
        default_factory=lambda: _float("SIDEWA_FACE_LOGIN_MARGIN", 0.03)
    )

    # ── Tavily: pemindaian pemberitaan media online ─────────────────────────
    tavily_api_key: str = field(
        default_factory=lambda: (
            os.getenv("SIDEWA_TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY", "")
        ).strip()
    )
    tavily_api_url: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_TAVILY_API_URL", "https://api.tavily.com/search"
        )
    )
    tavily_search_depth: str = field(
        default_factory=lambda: os.getenv("SIDEWA_TAVILY_SEARCH_DEPTH", "advanced")
    )
    tavily_max_results: int = field(
        default_factory=lambda: _int("SIDEWA_TAVILY_MAX_RESULTS", 10)
    )
    tavily_days: int = field(default_factory=lambda: _int("SIDEWA_TAVILY_DAYS", 180))

    # ── Gemini: analisis relevansi & sentimen pemberitaan ───────────────────
    # Dipakai bersama Tavily: Tavily menemukan artikel, Gemini menilai
    # relevansi dan sentimennya, lalu hasilnya dipadukan dengan leksikon lokal.
    gemini_api_key: str = field(
        default_factory=lambda: (
            os.getenv("SIDEWA_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        ).strip()
    )
    gemini_api_url: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_GEMINI_API_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
    )
    gemini_model: str = field(
        default_factory=lambda: os.getenv("SIDEWA_GEMINI_MODEL", "gemini-3.5-flash-lite")
    )
    gemini_live_model: str = field(
        default_factory=lambda: os.getenv("SIDEWA_GEMINI_LIVE_MODEL", "gemini-3.8-live")
    )
    gemini_live_technical_model: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_GEMINI_LIVE_TECHNICAL_MODEL",
            "gemini-3.8-live-extended-thinking",
        )
    )
    gemini_live_voice: str = field(
        default_factory=lambda: os.getenv("SIDEWA_GEMINI_LIVE_VOICE", "Aoede")
    )
    gemini_live_enabled: bool = field(
        default_factory=lambda: _bool("SIDEWA_GEMINI_LIVE_ENABLED", True)
    )
    gemini_live_thinking_level: str = field(
        default_factory=lambda: os.getenv("SIDEWA_GEMINI_LIVE_THINKING_LEVEL", "low")
    )
    gemini_timeout: int = field(default_factory=lambda: _int("SIDEWA_GEMINI_TIMEOUT", 60))
    gemini_max_output_tokens: int = field(
        default_factory=lambda: _int("SIDEWA_GEMINI_MAX_OUTPUT_TOKENS", 4096)
    )
    gemini_analysis_enabled: bool = field(
        default_factory=lambda: _bool("SIDEWA_GEMINI_ANALYSIS_ENABLED", True)
    )
    gemini_refine_query: bool = field(
        default_factory=lambda: _bool("SIDEWA_GEMINI_REFINE_QUERY", True)
    )
    gemini_filter_irrelevant: bool = field(
        default_factory=lambda: _bool("SIDEWA_GEMINI_FILTER_IRRELEVANT", True)
    )
    gemini_score_weight: float = field(
        default_factory=lambda: _float("SIDEWA_GEMINI_SCORE_WEIGHT", 0.7)
    )

    # ── Resolusi identitas anggota untuk penyaringan berita ─────────────────
    member_identity_file: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "SIDEWA_MEMBER_IDENTITY_FILE",
                str(BASE_DIR / "data" / "member_identity.json"),
            )
        )
    )
    sentiment_year_from: int = field(
        default_factory=lambda: _int("SIDEWA_SENTIMENT_YEAR_FROM", 2024)
    )
    sentiment_year_to: int = field(
        default_factory=lambda: _int("SIDEWA_SENTIMENT_YEAR_TO", 0)
    )
    sentiment_location: str = field(
        default_factory=lambda: os.getenv("SIDEWA_SENTIMENT_LOCATION", "Provinsi Riau")
    )
    gemini_min_identity_score: float = field(
        default_factory=lambda: _float("SIDEWA_GEMINI_MIN_IDENTITY_SCORE", 0.65)
    )
    gemini_require_identity: bool = field(
        default_factory=lambda: _bool("SIDEWA_GEMINI_REQUIRE_IDENTITY", True)
    )

    # ── Seleksi foto AI di ruang kerja Humas ────────────────────────────────
    # Setiap pengguna memakai kunci Gemini sendiri; kuota diatur per kunci.
    photo_selection_enabled: bool = field(
        default_factory=lambda: _bool("SIDEWA_PHOTO_SELECTION_ENABLED", True)
    )
    photo_selection_model: str = field(
        default_factory=lambda: os.getenv(
            "SIDEWA_PHOTO_SELECTION_MODEL", "gemini-3.5-flash-lite"
        )
    )
    photo_selection_rpm_default: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_RPM", 15)
    )
    photo_selection_rpd_default: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_RPD", 500)
    )
    photo_selection_tpm_default: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_TPM", 250000)
    )
    photo_selection_max_photos: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_MAX_PHOTOS", 24)
    )
    photo_selection_workers: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_WORKERS", 1)
    )
    photo_selection_sync: bool = field(
        default_factory=lambda: _bool("SIDEWA_PHOTO_SELECTION_SYNC", False)
    )
    photo_selection_timeout: int = field(
        default_factory=lambda: _int("SIDEWA_PHOTO_SELECTION_TIMEOUT", 90)
    )

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

    # ── Supabase: database utama (source of truth) ──────────────────────────
    # Runtime memakai transaction pooler (port 6543); operasi skema/resync
    # memakai session pooler (port 5432).
    supabase_database_url: str = field(
        default_factory=lambda: os.getenv("SIDEWA_SUPABASE_DATABASE_URL", "")
    )
    supabase_admin_database_url: str = field(
        default_factory=lambda: os.getenv("SIDEWA_SUPABASE_ADMIN_DATABASE_URL", "")
    )

    # ── Sinkronisasi lokal → Supabase ───────────────────────────────────────
    sync_enabled: bool = field(default_factory=lambda: _bool("SIDEWA_SYNC_ENABLED", False))
    sync_interval: int = field(default_factory=lambda: _int("SIDEWA_SYNC_INTERVAL", 5))
    sync_batch: int = field(default_factory=lambda: _int("SIDEWA_SYNC_BATCH", 200))
    sync_hydrate_on_empty: bool = field(
        default_factory=lambda: _bool("SIDEWA_SYNC_HYDRATE_ON_EMPTY", True)
    )
    sync_pull_on_start: bool = field(
        default_factory=lambda: _bool("SIDEWA_SYNC_PULL_ON_START", False)
    )

    # ── Media: Hugging Face S3 (S3-compatible) ──────────────────────────────
    hf_s3_bucket: str = field(default_factory=lambda: os.getenv("SIDEWA_HF_S3_BUCKET", ""))
    hf_s3_endpoint: str = field(
        default_factory=lambda: os.getenv("SIDEWA_HF_S3_ENDPOINT", "").rstrip("/")
    )
    hf_s3_region: str = field(default_factory=lambda: os.getenv("SIDEWA_HF_S3_REGION", "us-east-1"))
    hf_s3_access_key_id: str = field(
        default_factory=lambda: os.getenv("SIDEWA_HF_S3_ACCESS_KEY_ID", "")
    )
    hf_s3_secret_access_key: str = field(
        default_factory=lambda: os.getenv("SIDEWA_HF_S3_SECRET_ACCESS_KEY", "")
    )
    hf_s3_prefix: str = field(
        default_factory=lambda: os.getenv("SIDEWA_HF_S3_PREFIX", "sidewa/media").strip("/")
    )
    media_sync_enabled: bool = field(
        default_factory=lambda: _bool("SIDEWA_MEDIA_SYNC_ENABLED", True)
    )
    media_sync_interval: int = field(
        default_factory=lambda: _int("SIDEWA_MEDIA_SYNC_INTERVAL", 30)
    )
    media_cache_on_demand: bool = field(
        default_factory=lambda: _bool("SIDEWA_MEDIA_CACHE_ON_DEMAND", True)
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_database_url or self.supabase_admin_database_url)

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def gemini_live_available(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_live_enabled)

    @property
    def hf_s3_configured(self) -> bool:
        return bool(
            self.hf_s3_bucket
            and self.hf_s3_endpoint
            and self.hf_s3_access_key_id
            and self.hf_s3_secret_access_key
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        photos = max(self.max_photos_per_activity, self.photo_selection_max_photos)
        return self.max_upload_bytes * photos + 2 * 1024 * 1024

    def ensure_dirs(self) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        (self.media_root / "activities").mkdir(exist_ok=True)
        (self.media_root / "members").mkdir(exist_ok=True)
        (self.media_root / "staff").mkdir(exist_ok=True)
        (self.media_root / "selection").mkdir(exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", "", 1))
            if not db_path.is_absolute():
                db_path = BASE_DIR / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
