#!/bin/sh
set -eu

echo "[sidewa] Menyiapkan database…"
python -m app.cli init-db

if ! command -v rclone >/dev/null 2>&1; then
    echo "[sidewa] PERINGATAN: rclone tidak ditemukan; media tidak disinkronkan ke HF S3." >&2
fi

# Tidak ada seed otomatis. Data production (Supabase + HF S3) tidak boleh
# diisi ulang saat container start/restart.

echo "[sidewa] Menjalankan aplikasi…"
exec "$@"
