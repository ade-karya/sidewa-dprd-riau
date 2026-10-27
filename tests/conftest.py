"""Konfigurasi pengujian SIDEWA."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient


def _prepare_env(tmp_path, demo: bool = False, secret: str | None = None):
    db = tmp_path / "sidewa-test.db"
    media = tmp_path / "media"
    os.environ["SIDEWA_ENV"] = "testing"
    os.environ["SIDEWA_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["SIDEWA_MEDIA_ROOT"] = str(media)
    os.environ["SIDEWA_SECRET_KEY"] = secret or ("x" * 48)
    os.environ["SIDEWA_BOOTSTRAP_ADMIN_PASSWORD"] = "Super#Test2026"
    os.environ["SIDEWA_BOOTSTRAP_ADMIN_USERNAME"] = "superadmin"
    os.environ["SIDEWA_BOOTSTRAP_ADMIN_NAME"] = "Super Admin Test"
    os.environ["SIDEWA_DEMO_MODE"] = "true" if demo else "false"
    os.environ["SIDEWA_COOKIE_SECURE"] = "false"
    os.environ["SIDEWA_FACE_WORKERS"] = "1"
    os.environ["SIDEWA_LOG_LEVEL"] = "WARNING"
    # Isolasi pengujian: jangan pernah memanggil layanan eksternal secara nyata.
    os.environ["SIDEWA_TAVILY_API_KEY"] = ""
    os.environ["SIDEWA_GEMINI_API_KEY"] = ""
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    return db, media


def _import_app():
    from app.database import init_db
    from app.main import app

    init_db()
    return app


@pytest.fixture
def client(tmp_path):
    _prepare_env(tmp_path, demo=False)
    app = _import_app()
    with TestClient(app) as test_client:
        yield test_client, tmp_path


@pytest.fixture
def seeded_client(tmp_path):
    _prepare_env(tmp_path, demo=True)
    app = _import_app()
    from app.database import SessionLocal
    from app.services.seed import seed_demo

    db = SessionLocal()
    try:
        seed_demo(db, force=True)
    finally:
        db.close()
    with TestClient(app) as test_client:
        yield test_client, tmp_path


def get_csrf(client: TestClient) -> str:
    import re

    response = client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, "Token CSRF tidak ditemukan pada halaman login"
    return match.group(1)


def login(client: TestClient, username: str, password: str, csrf: str | None = None) -> None:
    token = csrf or get_csrf(client)
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token, "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
