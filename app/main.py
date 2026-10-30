"""Entry point aplikasi SIDEWA."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import settings
from .database import SessionLocal, init_db
from .models import User
from .routers import (
    activities,
    api,
    audit,
    auth,
    commissions,
    dashboard,
    guide,
    humas_staff,
    media,
    member_dashboard,
    members,
    photo_selection,
    search,
    system,
    users,
)
from .security import PasswordPolicyError, hash_password, validate_password_strength
from .services import face_engine, jobs, photo_curator, supabase_sync
from .templating import render

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("sidewa")


def _client_scheme(request: Request) -> str:
    """Skema yang dipakai klien, dengan menghormati header Cloudflare/proxy."""
    visitor = request.headers.get("cf-visitor", "")
    marker = '"scheme":"'
    if marker in visitor:
        value = visitor.split(marker, 1)[1].split('"', 1)[0].strip().lower()
        if value in {"http", "https"}:
            return value
    return (
        request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    HTTPS_EXEMPT_PATHS = {
        "/healthz",
        "/readyz",
        "/metrics",
        "/robots.txt",
        "/manifest.webmanifest",
        "/favicon.ico",
    }

    async def dispatch(self, request: Request, call_next):
        if settings.is_production:
            scheme = _client_scheme(request)
            if scheme == "http" and request.url.path not in self.HTTPS_EXEMPT_PATHS:
                secure_url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(secure_url, status_code=308)
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request gagal method=%s path=%s request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' https://static.cloudflareinsights.com; "
            "font-src 'self'; "
            "connect-src 'self' https://cloudflareinsights.com; "
            "frame-src https://www.openstreetmap.org https://www.google.com; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers.setdefault("Cache-Control", "no-store")
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            message = f"Ukuran unggahan melebihi batas {settings.max_upload_mb} MB per foto."
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": message}, status_code=413)
            return PlainTextResponse(message, status_code=413)
        return await call_next(request)


def _bootstrap_admin() -> None:
    username = settings.bootstrap_admin_username.strip()
    password = settings.bootstrap_admin_password
    if not username or not password:
        return
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            return
        validate_password_strength(password)
        db.add(
            User(
                username=username,
                full_name=settings.bootstrap_admin_name,
                password_hash=hash_password(password),
                role="superadmin",
                is_active=True,
                must_change_password=True,
            )
        )
        db.commit()
        logger.warning("Akun superadmin bootstrap '%s' dibuat. Segera ganti kata sandi.", username)
    except PasswordPolicyError as exc:
        logger.error("Kata sandi bootstrap admin tidak memenuhi kebijakan: %s", exc)
    except Exception:
        logger.exception("Gagal membuat akun bootstrap admin")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.ensure_dirs()
    _bootstrap_admin()
    if not face_engine.engine.available:
        logger.warning("Mesin wajah tidak tersedia: %s", face_engine.engine.error)
    queued = jobs.requeue_pending()
    if queued:
        logger.info("%s foto dimasukkan kembali ke antrean pemrosesan wajah.", queued)
    curator_runs = photo_curator.requeue_runs()
    if curator_runs:
        logger.info("%s sesi seleksi foto dimasukkan kembali ke antrean.", curator_runs)
    supabase_sync.bootstrap()
    logger.info(
        "SIDEWA %s siap — env=%s database=%s",
        __version__,
        settings.app_env,
        settings.database_url.split("://", 1)[0],
    )
    yield
    jobs.shutdown()
    photo_curator.shutdown()
    supabase_sync.flush_and_shutdown()


def create_app() -> FastAPI:
    application = FastAPI(
        title="SIDEWA API",
        description=(
            "API dokumentasi kegiatan DPRD Provinsi Riau dengan pencarian wajah. "
            "Autentikasi menggunakan sesi (cookie) atau Bearer token API."
        ),
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    if settings.trusted_hosts:
        application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )
    application.add_middleware(GZipMiddleware, minimum_size=1200)
    application.add_middleware(MaxBodySizeMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="sidewa_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    static_dir = Path(__file__).resolve().parent / "static"
    application.mount("/static", StaticFiles(directory=static_dir), name="static")

    application.include_router(system.router)
    application.include_router(auth.router)
    application.include_router(dashboard.router)
    application.include_router(guide.router)
    application.include_router(member_dashboard.router)
    application.include_router(humas_staff.router)
    application.include_router(photo_selection.router)
    application.include_router(activities.router)
    application.include_router(search.router)
    application.include_router(members.router)
    application.include_router(commissions.router)
    application.include_router(users.router)
    application.include_router(audit.router)
    application.include_router(media.router)
    application.include_router(api.router)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        location = exc.headers.get("Location") if exc.headers else None
        if exc.status_code in {301, 302, 303, 307, 308} and location:
            return RedirectResponse(location, status_code=exc.status_code)
        wants_json = request.url.path.startswith(
            "/api/"
        ) or "application/json" in request.headers.get("accept", "")
        message = exc.detail if isinstance(exc.detail, str) else "Terjadi kesalahan."
        if wants_json:
            return JSONResponse(
                {"detail": message},
                status_code=exc.status_code,
                headers=exc.headers,
            )
        titles = {
            400: "Permintaan tidak valid",
            401: "Autentikasi diperlukan",
            403: "Akses ditolak",
            404: "Halaman tidak ditemukan",
            413: "Berkas terlalu besar",
            429: "Terlalu banyak permintaan",
        }
        user = getattr(request.state, "user", None)
        return render(
            request,
            "errors/error.html",
            user=user,
            status_code=exc.status_code,
            code=exc.status_code,
            title=titles.get(exc.status_code, "Terjadi kesalahan"),
            message=message,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.errors()}, status_code=422)
        return render(
            request,
            "errors/error.html",
            status_code=422,
            code=422,
            title="Data tidak valid",
            message="Periksa kembali isian formulir Anda.",
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error request_id=%s", getattr(request.state, "request_id", "-"))
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Terjadi kesalahan pada server."}, status_code=500)
        return render(
            request,
            "errors/error.html",
            status_code=500,
            code=500,
            title="Terjadi kesalahan",
            message="Kami tidak dapat memproses permintaan Anda. Silakan coba lagi.",
        )

    return application


app = create_app()
