"""Sinkronisasi local-first ke Supabase (mode cache lokal, opsional).

Arsitektur ini hanya dipakai bila ``SIDEWA_SYNC_ENABLED=true`` dan database
utama masih berupa PostgreSQL lokal. Pada mode produksi default, aplikasi
terhubung langsung ke Supabase sehingga modul ini tidak menjalankan worker.

- Aplikasi membaca/menulis ke PostgreSQL lokal (cache operasional).
- Trigger PostgreSQL mencatat setiap perubahan ke tabel ``sync_outbox``.
- Worker di proses aplikasi mengirim outbox ke Supabase secara batch.
- Jika database lokal kosong, data dipulihkan (hydrate) dari Supabase.
- Media ditangani terpisah oleh ``media_sync`` (Hugging Face S3 via boto3).

Supabase tetap menjadi sumber kebenaran (source of truth); PostgreSQL lokal
hanya buffer/cache untuk mengurangi koneksi dan beban Supabase.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from ..database import SCHEMA_LOCK_KEY, Base
from ..database import engine as local_engine

logger = logging.getLogger("sidewa.sync")

# Urutan aman untuk foreign key saat copy/hydrate.
TABLE_ORDER = [
    "commissions",
    "users",
    "members",
    "member_faces",
    "member_accounts",
    "member_face_logins",
    "humas_staff",
    "humas_staff_accounts",
    "humas_staff_face_logins",
    "sentiment_runs",
    "media_mentions",
    "photo_selection_skills",
    "ai_photo_settings",
    "activities",
    "press_releases",
    "release_skills",
    "activity_photos",
    "face_detections",
    "activity_members",
    "photo_selection_runs",
    "photo_selection_items",
    "ai_request_logs",
    "audit_logs",
    "api_tokens",
    "activity_commissions",
]
SYNC_TABLES = set(TABLE_ORDER)
ID_TABLES = [name for name in TABLE_ORDER if name != "activity_commissions"]

ADVISORY_LOCK_KEY = 0x53494445  # "SIDE"
BOOTSTRAP_LOCK_KEY = 0x53494446  # "SIDF"
SCHEMA_LOCK_KEY = 0x53494447  # "SIDG"

_engine_lock = threading.Lock()
_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[Session]] = {}
_worker: SyncWorker | None = None
_worker_lock = threading.Lock()
_schema_ready = False
_last_schema_attempt = 0.0
_last_sync_at: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Konfigurasi & engine
# ─────────────────────────────────────────────────────────────────────────────


def enabled() -> bool:
    """Aktif hanya untuk mode cache lokal (PostgreSQL lokal + Supabase)."""
    return bool(
        settings.sync_enabled
        and settings.supabase_configured
        and settings.database_url.startswith("postgresql")
    )


def _build_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=1, max_overflow=1, pool_recycle=300)
        connect_args: dict[str, Any] = {"connect_timeout": 15}
        try:
            if make_url(url).port == 6543:
                # PgBouncer transaction mode tidak mendukung prepared statements.
                connect_args["prepare_threshold"] = None
        except Exception:  # pragma: no cover - URL tidak valid ditangani saat connect
            pass
        kwargs["connect_args"] = connect_args
    return create_engine(url, **kwargs)


def _engine_for(kind: str) -> Engine:
    with _engine_lock:
        if kind in _engines:
            return _engines[kind]
        if kind == "admin":
            url = settings.supabase_admin_database_url or settings.supabase_database_url
        else:
            url = settings.supabase_database_url or settings.supabase_admin_database_url
        if not url:
            raise RuntimeError("URL database Supabase belum dikonfigurasi.")
        engine = _build_engine(url)
        _engines[kind] = engine
        _factories[kind] = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, class_=Session
        )
        return engine


def sync_engine() -> Engine:
    return _engine_for("sync")


def admin_engine() -> Engine:
    return _engine_for("admin")


@contextmanager
def sync_session() -> Iterator[Session]:
    factory = _factories.get("sync")
    if factory is None:
        _engine_for("sync")
        factory = _factories["sync"]
    session = factory()
    try:
        yield session
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Skema lokal: outbox + trigger
# ─────────────────────────────────────────────────────────────────────────────

_LOCAL_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sync_outbox (
        id BIGSERIAL PRIMARY KEY,
        entity VARCHAR(64) NOT NULL,
        entity_id VARCHAR(128) NOT NULL DEFAULT '',
        op VARCHAR(10) NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sync_outbox_created ON sync_outbox (id)",
    """
    CREATE TABLE IF NOT EXISTS media_sync (
        path TEXT PRIMARY KEY,
        size BIGINT NOT NULL DEFAULT 0,
        mtime DOUBLE PRECISION NOT NULL DEFAULT 0,
        uploaded_at TIMESTAMPTZ,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
    )
    """,
    "ALTER TABLE media_sync ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0",
    """
    CREATE TABLE IF NOT EXISTS media_sync_deletions (
        path TEXT PRIMARY KEY,
        queued_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

_CAPTURE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION sidewa_capture_change() RETURNS trigger AS $$
DECLARE
    payload jsonb;
    entity_id text;
BEGIN
    IF COALESCE(current_setting('sidewa.sync_suppress', true), '') = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    IF TG_OP = 'DELETE' THEN
        payload := to_jsonb(OLD);
    ELSE
        payload := to_jsonb(NEW);
    END IF;

    IF TG_TABLE_NAME = 'activity_commissions' THEN
        entity_id := COALESCE(payload->>'activity_id', '') || ':' ||
                     COALESCE(payload->>'commission_id', '');
    ELSE
        entity_id := COALESCE(payload->>'id', '');
    END IF;

    INSERT INTO sync_outbox (entity, entity_id, op, payload)
    VALUES (TG_TABLE_NAME, entity_id, TG_OP, payload);

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""


def install_local_schema() -> None:
    """Pasang outbox, trigger, dan tabel bantu media pada database aplikasi."""
    if not (settings.sync_enabled or settings.media_sync_enabled):
        return
    if not settings.database_url.startswith("postgresql"):
        logger.warning(
            "Sinkronisasi Supabase/HF S3 membutuhkan PostgreSQL lokal; "
            "fitur sinkronisasi dinonaktifkan untuk database ini."
        )
        return

    try:
        with local_engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": SCHEMA_LOCK_KEY},
            )
            for statement in _LOCAL_SCHEMA_STATEMENTS:
                conn.execute(text(statement))
            conn.execute(text(_CAPTURE_FUNCTION_SQL))
            if settings.sync_enabled:
                for table in TABLE_ORDER:
                    conn.execute(
                        text(
                            f'CREATE OR REPLACE TRIGGER sidewa_sync '
                            f'AFTER INSERT OR UPDATE OR DELETE ON public."{table}" '
                            f"FOR EACH ROW EXECUTE FUNCTION sidewa_capture_change()"
                        )
                    )
    except Exception:
        logger.exception("Gagal memasang skema sinkronisasi lokal")


# ─────────────────────────────────────────────────────────────────────────────
# Skema Supabase
# ─────────────────────────────────────────────────────────────────────────────


def _supabase_roles(conn) -> set[str]:
    try:
        rows = conn.execute(
            text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        )
        return {row[0] for row in rows}
    except Exception:
        return set()


def _ensure_sequences(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in ID_TABLES:
            sequence = conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": f"public.{table}"},
            ).scalar()
            if not sequence:
                continue
            conn.execute(
                text(
                    f'SELECT setval(CAST(:seq AS regclass), '
                    f'COALESCE((SELECT MAX(id) FROM public."{table}"), 1), '
                    f'(SELECT COUNT(*) > 0 FROM public."{table}"))'
                ),
                {"seq": sequence},
            )


def init_supabase_schema() -> None:
    """Buat tabel di Supabase, aktifkan RLS, dan cabut akses anon."""
    global _schema_ready
    if not enabled():
        return
    engine = admin_engine()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        roles = _supabase_roles(conn)
        for table in TABLE_ORDER:
            conn.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
            for role in roles:
                conn.execute(text(f'REVOKE ALL ON TABLE public."{table}" FROM {role}'))
            if table in ID_TABLES:
                sequence = conn.execute(
                    text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                    {"table_name": f"public.{table}"},
                ).scalar()
                if sequence:
                    for role in roles:
                        conn.execute(text(f"REVOKE ALL ON SEQUENCE {sequence} FROM {role}"))

    _ensure_sequences(engine)
    _schema_ready = True
    logger.info("Skema Supabase siap (%s tabel).", len(TABLE_ORDER))


def _ensure_schema_ready(*, force: bool = False, wait: bool = False) -> bool:
    """Pastikan skema Supabase siap, dengan lock transaksi yang auto-release.

    Lock memakai ``pg_advisory_xact_lock`` sehingga otomatis dilepas saat
    transaksi selesai (commit/rollback). Ini mencegah lock "nyangkut" di
    connection pool seperti pada lock level-sesi.
    """
    global _schema_ready, _last_schema_attempt
    if _schema_ready and not force:
        return True
    now = time.monotonic()
    if not force and now - _last_schema_attempt < 60:
        return False
    try:
        with local_engine.begin() as conn:
            if wait:
                conn.execute(text("SET LOCAL lock_timeout = '60s'"))
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": SCHEMA_LOCK_KEY},
                )
            else:
                acquired = conn.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": SCHEMA_LOCK_KEY},
                ).scalar()
                if not acquired:
                    return False
            _last_schema_attempt = time.monotonic()
            init_supabase_schema()
        return True
    except Exception as exc:
        logger.warning("Supabase belum dapat diakses: %s", exc)
        return False


def _adopt_existing_schema() -> bool:
    """Tandai skema siap bila semua tabel sudah ada, tanpa menjalankan DDL.

    Dipakai worker non-leader agar tidak mengulang ``create_all``/RLS yang
    mahal, sekaligus membuat ``/readyz`` akurat di semua worker.
    """
    global _schema_ready
    if _schema_ready:
        return True
    if not enabled():
        return False
    values = ", ".join(f"('{name}')" for name in TABLE_ORDER)
    try:
        with sync_engine().connect() as conn:
            missing = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM (VALUES {values}) AS t(name) "
                    "WHERE to_regclass('public.' || t.name) IS NULL"
                )
            ).scalar()
    except Exception:
        return False
    if int(missing or 0) == 0:
        _schema_ready = True
        logger.info("Skema Supabase terdeteksi siap (diadopsi tanpa DDL).")
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Outbox → Supabase
# ─────────────────────────────────────────────────────────────────────────────


def _upsert_remote(conn, entity: str, payload: dict[str, Any]) -> None:
    table = Base.metadata.tables[entity]
    columns = [column.name for column in table.columns]
    column_list = ", ".join(f'"{name}"' for name in columns)
    if entity == "activity_commissions":
        conflict = "ON CONFLICT (activity_id, commission_id) DO NOTHING"
    else:
        updates = ", ".join(
            f'"{name}" = EXCLUDED."{name}"' for name in columns if name != "id"
        )
        conflict = f'ON CONFLICT ("id") DO UPDATE SET {updates}'
    sql = (
        f'INSERT INTO public."{entity}" ({column_list}) '
        f'SELECT {column_list} '
        f'FROM jsonb_populate_record(NULL::public."{entity}", CAST(:payload AS jsonb)) '
        f"{conflict}"
    )
    conn.execute(text(sql), {"payload": json.dumps(payload, ensure_ascii=False)})


def _delete_remote(conn, entity: str, payload: dict[str, Any]) -> None:
    if entity == "activity_commissions":
        conn.execute(
            text(
                'DELETE FROM public."activity_commissions" '
                "WHERE activity_id = :activity_id AND commission_id = :commission_id"
            ),
            {
                "activity_id": payload.get("activity_id"),
                "commission_id": payload.get("commission_id"),
            },
        )
        return
    if payload.get("id") is None:
        return
    conn.execute(
        text(f'DELETE FROM public."{entity}" WHERE id = :id'),
        {"id": payload["id"]},
    )


def _apply_row(conn, row) -> None:
    entity = row["entity"]
    if entity not in SYNC_TABLES:
        logger.warning("Entitas outbox tidak dikenal: %s", entity)
        return
    payload = json.loads(row["payload"])
    if row["op"].upper() == "DELETE":
        _delete_remote(conn, entity, payload)
    else:
        _upsert_remote(conn, entity, payload)


def _delete_outbox(ids: list[int]) -> None:
    if not ids:
        return
    statement = text("DELETE FROM sync_outbox WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    with local_engine.begin() as conn:
        conn.execute(statement, {"ids": ids})


def _mark_error(outbox_id: int, exc: Exception) -> None:
    try:
        with local_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE sync_outbox SET attempts = attempts + 1, "
                    "last_error = :error WHERE id = :id"
                ),
                {"error": str(exc)[:1000], "id": outbox_id},
            )
    except Exception:
        logger.exception("Gagal menandai error outbox #%s", outbox_id)


def process_outbox(limit: int | None = None) -> int:
    """Kirim satu batch outbox ke Supabase. Mengembalikan jumlah baris terkirim."""
    global _last_sync_at
    if not enabled():
        return 0
    if not _ensure_schema_ready():
        return 0

    with local_engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT id, entity, entity_id, op, payload::text AS payload "
                    "FROM sync_outbox ORDER BY id LIMIT :limit"
                ),
                {"limit": limit or settings.sync_batch},
            )
            .mappings()
            .all()
        )
    if not rows:
        return 0

    try:
        with sync_engine().begin() as remote:
            for row in rows:
                _apply_row(remote, row)
    except Exception as exc:
        logger.warning("Batch sinkronisasi gagal (%s); mencoba per baris.", exc)
        applied = 0
        for row in rows:
            try:
                with sync_engine().begin() as remote:
                    _apply_row(remote, row)
            except Exception as row_exc:
                _mark_error(row["id"], row_exc)
                logger.error(
                    "Gagal sinkron %s#%s: %s", row["entity"], row["entity_id"], row_exc
                )
                # Hentikan batch agar urutan FK tetap terjaga.
                break
            else:
                _delete_outbox([row["id"]])
                applied += 1
    else:
        _delete_outbox([row["id"] for row in rows])
        applied = len(rows)

    if applied:
        _last_sync_at = datetime.now(UTC).isoformat()
        logger.info("%s perubahan tersinkron ke Supabase.", applied)
    return applied


# ─────────────────────────────────────────────────────────────────────────────
# Resync / hydrate
# ─────────────────────────────────────────────────────────────────────────────


def _chunks(items: list[dict[str, Any]], size: int = 500):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def clear_outbox() -> None:
    try:
        with local_engine.begin() as conn:
            conn.execute(text("DELETE FROM sync_outbox"))
    except Exception:
        logger.exception("Gagal membersihkan outbox lokal")


def truncate_supabase() -> None:
    tables = ", ".join(f'public."{name}"' for name in TABLE_ORDER)
    with admin_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def copy_local_to_supabase(*, truncate: bool = False) -> dict[str, int]:
    """Salin seluruh data lokal ke Supabase (upsert, opsional truncate dulu)."""
    if settings.is_production:
        raise RuntimeError(
            "copy_local_to_supabase() diblokir di production: data Supabase "
            "tidak boleh diisi ulang."
        )
    if not enabled():
        raise RuntimeError("Sinkronisasi Supabase belum dikonfigurasi.")
    if not _ensure_schema_ready(force=True, wait=True):
        raise RuntimeError("Skema Supabase belum siap; resync dibatalkan.")
    counts: dict[str, int] = {}

    with admin_engine().begin() as remote:
        if truncate:
            tables = ", ".join(f'public."{name}"' for name in TABLE_ORDER)
            remote.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))

        for entity in TABLE_ORDER:
            table = Base.metadata.tables[entity]
            with local_engine.connect() as local:
                rows = [dict(row) for row in local.execute(select(table)).mappings()]
            counts[entity] = len(rows)
            for chunk in _chunks(rows):
                statement = pg_insert(table).values(chunk)
                if entity == "activity_commissions":
                    statement = statement.on_conflict_do_nothing(
                        index_elements=["activity_id", "commission_id"]
                    )
                else:
                    updates = {
                        column.name: getattr(statement.excluded, column.name)
                        for column in table.columns
                        if column.name != "id"
                    }
                    statement = statement.on_conflict_do_update(
                        index_elements=["id"], set_=updates
                    )
                remote.execute(statement)

    _ensure_sequences(admin_engine())
    clear_outbox()
    logger.info("Resync lokal → Supabase selesai: %s", counts)
    return counts


def local_is_empty() -> bool:
    try:
        with local_engine.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0) == 0
    except Exception:
        return True


def hydrate_from_supabase(*, force: bool = False) -> dict[str, int]:
    """Pulihkan cache lokal dari Supabase (source of truth)."""
    if not enabled():
        raise RuntimeError("Sinkronisasi Supabase belum dikonfigurasi.")
    if not force and not local_is_empty():
        return {"skipped": 1}

    if not _ensure_schema_ready(force=True, wait=True):
        raise RuntimeError("Skema Supabase belum siap; hydrate dibatalkan.")
    counts: dict[str, int] = {}

    with local_engine.begin() as local:
        local.execute(text("SET LOCAL sidewa.sync_suppress = 'on'"))
        tables = ", ".join(f'public."{name}"' for name in TABLE_ORDER)
        local.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))

        with admin_engine().connect() as remote:
            for entity in TABLE_ORDER:
                table = Base.metadata.tables[entity]
                rows = [dict(row) for row in remote.execute(select(table)).mappings()]
                counts[entity] = len(rows)
                for chunk in _chunks(rows):
                    local.execute(table.insert(), chunk)

    clear_outbox()
    _ensure_sequences(local_engine)
    logger.info("Hydrate Supabase → lokal selesai: %s", counts)
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Lock & worker
# ─────────────────────────────────────────────────────────────────────────────


def _try_lock(key: int):
    """Ambil advisory lock level-sesi (untuk leader election worker).

    Koneksi pemegang lock **tidak boleh** dikembalikan ke pool selama lock
    masih dipegang. Pemanggil wajib memakai :func:`_release_lock`.
    """
    try:
        conn = local_engine.connect()
    except Exception:
        return None
    try:
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ).scalar()
        conn.commit()
    except Exception:
        conn.invalidate()
        conn.close()
        return None
    if acquired:
        return conn
    conn.close()
    return None


def _release_lock(conn, key: int) -> None:
    """Lepas advisory lock dan pastikan tidak terbawa ke connection pool."""
    released = False
    try:
        released = bool(
            conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": key}
            ).scalar()
        )
        conn.commit()
    except Exception:
        logger.exception("Gagal melepas advisory lock %s", key)
    finally:
        if not released:
            # Putuskan koneksi DBAPI agar lock level-sesi pasti dilepas oleh
            # PostgreSQL, bukan tertinggal di koneksi yang dipakai ulang pool.
            try:
                conn.invalidate()
            except Exception:
                pass
        conn.close()


class SyncWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="sidewa-supabase-sync", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _run(self) -> None:
        lock_conn = None
        while not self._stop.is_set():
            try:
                if lock_conn is None:
                    lock_conn = _try_lock(ADVISORY_LOCK_KEY)
                if lock_conn is not None:
                    # Verifikasi koneksi pemegang lock masih hidup.
                    try:
                        lock_conn.execute(text("SELECT 1"))
                        lock_conn.commit()
                    except Exception:
                        lock_conn.invalidate()
                        lock_conn.close()
                        lock_conn = None
                        continue
                    process_outbox()
                else:
                    # Worker non-leader tetap menyiapkan skema agar /readyz
                    # akurat, tanpa memblokir siklus (non-blocking lock).
                    if not _ensure_schema_ready(wait=False):
                        _adopt_existing_schema()
            except Exception:
                logger.exception("Siklus sinkronisasi gagal")
            self._stop.wait(max(1, settings.sync_interval))

        if lock_conn is not None:
            _release_lock(lock_conn, ADVISORY_LOCK_KEY)


def start_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = SyncWorker()
            _worker.start()
            logger.info(
                "Worker sinkronisasi Supabase aktif (interval=%ss, batch=%s).",
                settings.sync_interval,
                settings.sync_batch,
            )


def _stop_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
            _worker = None


def _dispose_engines() -> None:
    for engine in list(_engines.values()):
        try:
            engine.dispose()
        except Exception:
            pass


def shutdown() -> None:
    _stop_worker()
    _dispose_engines()


def flush_and_shutdown() -> None:
    """Hentikan worker, kirim outbox terakhir, lalu tutup koneksi."""
    _stop_worker()
    try:
        if enabled():
            process_outbox()
    except Exception:
        logger.exception("Gagal mengirim outbox terakhir saat shutdown")
    _dispose_engines()


def bootstrap() -> None:
    """Siapkan skema, pulihkan cache bila kosong, lalu jalankan worker."""
    install_local_schema()
    if not enabled():
        if settings.sync_enabled:
            logger.warning("Sinkronisasi aktif tetapi Supabase belum dikonfigurasi.")
        return

    lock_conn = _try_lock(BOOTSTRAP_LOCK_KEY)
    if lock_conn is not None:
        try:
            if not _ensure_schema_ready(force=True, wait=True):
                logger.warning("Bootstrap sinkronisasi ditunda; Supabase belum siap.")
            else:
                if settings.sync_pull_on_start and not local_is_empty():
                    process_outbox()
                    hydrate_from_supabase(force=True)
                elif settings.sync_hydrate_on_empty and local_is_empty():
                    logger.info("Cache lokal kosong; memulihkan data dari Supabase…")
                    hydrate_from_supabase(force=True)
        except Exception:
            logger.exception("Bootstrap sinkronisasi gagal")
        finally:
            _release_lock(lock_conn, BOOTSTRAP_LOCK_KEY)
    else:
        # Proses lain sedang bootstrap. Adopsi skema yang sudah ada tanpa DDL;
        # worker akan mengulanginya pada siklus berikutnya bila perlu.
        if not _ensure_schema_ready(wait=False):
            _adopt_existing_schema()

    start_worker()


def status() -> dict[str, Any]:
    if not enabled():
        return {
            "enabled": False,
            "media_sync": bool(settings.media_sync_enabled and settings.hf_s3_configured),
        }
    try:
        with local_engine.connect() as conn:
            pending = int(conn.execute(text("SELECT COUNT(*) FROM sync_outbox")).scalar() or 0)
            errors = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM sync_outbox WHERE attempts > 0")
                ).scalar()
                or 0
            )
            oldest = conn.execute(text("SELECT MIN(created_at) FROM sync_outbox")).scalar()
            last_error = conn.execute(
                text(
                    "SELECT last_error FROM sync_outbox "
                    "WHERE last_error IS NOT NULL ORDER BY id DESC LIMIT 1"
                )
            ).scalar()
        return {
            "enabled": True,
            "schema_ready": _schema_ready,
            "pending": pending,
            "errors": errors,
            "oldest_pending": oldest.isoformat() if oldest else None,
            "last_error": last_error,
            "last_sync_at": _last_sync_at,
            "media_sync": bool(settings.media_sync_enabled and settings.hf_s3_configured),
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}
