# Deploy SIDEWA

## Docker Compose (disarankan)

```bash
cp .env.example .env
# Isi POSTGRES_PASSWORD, SIDEWA_SECRET_KEY, SIDEWA_TRUSTED_HOSTS
docker compose up -d --build
```

Stack: PostgreSQL 17, aplikasi FastAPI (4 worker), Nginx reverse proxy. Volume `media_data` dan `postgres_data`.

Muat data demo (opsional, hanya non-produksi):

```bash
SIDEWA_SEED_DEMO=true docker compose up -d
```

## Produksi tanpa Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit
python -m app.cli init-db
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
```

Gunakan supervisor/systemd untuk menjaga proses. Letakkan Nginx di depan untuk TLS dan rate limit.

## Backup

- Database: `pg_dump` (PostgreSQL) atau salin file SQLite saat aplikasi berhenti.
- Media: arsipkan direktori `SIDEWA_MEDIA_ROOT`.
- Simpan `.env` di tempat aman.
