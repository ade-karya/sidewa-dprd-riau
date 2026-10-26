#!/bin/sh
set -eu

echo "[sidewa] Menyiapkan database…"
python -m app.cli init-db

if [ "${SIDEWA_SEED_DEMO:-false}" = "true" ]; then
    echo "[sidewa] Memuat data demo…"
    python -m app.cli seed --force
fi

echo "[sidewa] Menjalankan aplikasi…"
exec "$@"
