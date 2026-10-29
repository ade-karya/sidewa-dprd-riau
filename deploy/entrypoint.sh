#!/bin/sh
set -eu

echo "[sidewa] Menyiapkan database…"
python -m app.cli init-db

# Tidak ada seed otomatis. Data production (Supabase + HF S3) tidak boleh
# diisi ulang saat container start/restart.

echo "[sidewa] Menjalankan aplikasi…"
exec "$@"
