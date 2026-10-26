"""Endpoint kesehatan, metrik, dan berkas sistem."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .. import __version__
from ..config import settings
from ..database import SessionLocal, db_health
from ..metrics import render as render_metrics
from ..models import ActivityPhoto
from ..services import face_engine

router = APIRouter(include_in_schema=False)


@router.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__, "service": "sidewa"}


@router.get("/readyz")
def readyz():
    db_ok = db_health()
    pending = 0
    if db_ok:
        db = SessionLocal()
        try:
            pending = (
                db.query(ActivityPhoto)
                .filter(ActivityPhoto.status.in_(["pending", "processing"]))
                .count()
            )
        finally:
            db.close()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "face_engine": "ok" if face_engine.engine.available else "unavailable",
        "pending_photos": pending,
        "version": __version__,
    }
    return JSONResponse(payload, status_code=200 if db_ok else 503)


@router.get("/metrics")
def metrics(request: Request):
    if settings.metrics_token:
        auth = request.headers.get("authorization", "")
        provided = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else ""
        if provided != settings.metrics_token:
            return PlainTextResponse("unauthorized\n", status_code=401)
    return PlainTextResponse(render_metrics(), media_type="text/plain; version=0.0.4")


@router.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {
            "name": f"{settings.app_name} — {settings.organization}",
            "short_name": settings.app_name,
            "start_url": "/",
            "display": "standalone",
            "background_color": "#FBF9FC",
            "theme_color": "#7E4890",
            "icons": [{"src": "/static/img/logo.svg", "sizes": "any", "type": "image/svg+xml"}],
        }
    )
