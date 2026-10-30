"""Koneksi database, sesi SQLAlchemy, dan utilitas inisialisasi."""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

logger = logging.getLogger("sidewa.database")

# Kunci advisory PostgreSQL agar beberapa worker uvicorn tidak berlomba
# membuat tabel/tipe yang sama saat start pertama setelah migrasi.
SCHEMA_LOCK_KEY = 730421


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        # Supabase transaction pooler (port 6543) berbagi koneksi backend di
        # antara banyak klien. Pool kecil + prepared statement dimatikan agar
        # sesi tidak saling bertabrakan.
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 5
        kwargs["pool_recycle"] = 1800
        connect_args: dict = {"connect_timeout": 15}
        try:
            if make_url(url).port == 6543:
                # PgBouncer transaction mode tidak mendukung prepared statements.
                connect_args["prepare_threshold"] = None
        except Exception:  # pragma: no cover - URL tidak valid ditangani saat connect
            pass
        kwargs["connect_args"] = connect_args
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (memastikan model terdaftar)

    settings.ensure_dirs()
    if engine.dialect.name == "postgresql":
        # Serialisasi DDL antar-worker. Tanpa ini, dua worker dapat mencoba
        # membuat tabel baru secara bersamaan dan gagal dengan "type already
        # exists" pada PostgreSQL.
        with engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": SCHEMA_LOCK_KEY},
            )
            Base.metadata.create_all(bind=conn)
    else:
        Base.metadata.create_all(bind=engine)

    # Tabel outbox, trigger perubahan, dan antrean media (khusus PostgreSQL).
    try:
        from .services import supabase_sync

        supabase_sync.install_local_schema()
    except Exception:
        logger.exception("Gagal menyiapkan skema sinkronisasi lokal")


def db_health() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
