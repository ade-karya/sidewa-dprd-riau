#!/bin/sh
set -eu

echo "[sidewa] Menyiapkan database…"
python -m app.cli init-db

if [ "${SIDEWA_SEED_DEMO:-false}" = "true" ]; then
    echo "[sidewa] Memuat data demo…"
    python -m app.cli seed --force
fi

# Pasang data & foto staf Humas resmi (idempoten). Foto resolusi penuh
# disalin dari seed_assets/staff_portraits sehingga server baru langsung
# memiliki potret default tanpa unggah manual.
if [ "${SIDEWA_SEED_STAFF:-true}" = "true" ]; then
    echo "[sidewa] Memasang data & foto staf Humas…"
    python -m app.cli seed-staff || \
        echo "[sidewa] Peringatan: data staf Humas gagal dimuat; aplikasi tetap dijalankan."
fi

echo "[sidewa] Menjalankan aplikasi…"
exec "$@"
