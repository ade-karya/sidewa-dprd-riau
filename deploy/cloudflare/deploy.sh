#!/usr/bin/env bash
# Deploy DewanKu edge gateway ke Cloudflare Workers dan/atau Pages.
#
# Pemakaian:
#   ./deploy.sh                 # Worker + Pages
#   ./deploy.sh worker          # Worker saja
#   ./deploy.sh pages           # Pages saja
#   ORIGIN=https://origin.dprd.riau.ai ./deploy.sh
#
# Autentikasi (pilih salah satu):
#   npx -y wrangler@4 login
#   export CLOUDFLARE_API_TOKEN=...
#   export CLOUDFLARE_ACCOUNT_ID=...
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-all}"
ORIGIN="${ORIGIN:-https://dprd.riau.ai}"
WRANGLER=(npx -y wrangler@4)

if [[ "$TARGET" != "all" && "$TARGET" != "worker" && "$TARGET" != "pages" ]]; then
  echo "Target tidak dikenal: $TARGET (pakai: all|worker|pages)" >&2
  exit 2
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx tidak ditemukan. Pasang Node.js 20+ terlebih dahulu." >&2
  exit 1
fi

echo "==> Origin: $ORIGIN"

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "==> CLOUDFLARE_API_TOKEN tidak diset; memakai sesi 'wrangler login' bila ada."
fi

if [[ "$TARGET" == "all" || "$TARGET" == "worker" ]]; then
  echo "==> Deploy Worker sidewa-edge"
  (
    cd "$SCRIPT_DIR/worker"
    "${WRANGLER[@]}" deploy --var "ORIGIN:${ORIGIN}"
  )
  echo "==> Worker selesai. Tambahkan custom domain di dashboard bila perlu."
fi

if [[ "$TARGET" == "all" || "$TARGET" == "pages" ]]; then
  echo "==> Deploy Pages sidewa-pages"
  (
    cd "$SCRIPT_DIR/pages"
    if ! "${WRANGLER[@]}" pages project list 2>/dev/null | grep -q "sidewa-pages"; then
      echo "    Membuat proyek Pages sidewa-pages…"
      "${WRANGLER[@]}" pages project create sidewa-pages --production-branch main
    fi
    "${WRANGLER[@]}" pages deploy
  )
  if [[ "$ORIGIN" != "https://dprd.riau.ai" ]]; then
    echo "PENTING: set variabel ORIGIN=$ORIGIN di dashboard Pages"
    echo "         (Settings → Environment variables) untuk environment Production."
  fi
  echo "==> Pages selesai."
fi

echo "==> Selesai. Uji /__edge/health dan /readyz pada URL hasil deploy."
