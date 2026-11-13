# Deploy SIDEWA di Cloudflare Workers & Pages

Dokumen ini menjelaskan cara menaruh SIDEWA di depan Cloudflare **Workers** dan
**Pages** sebagai *edge gateway*.

> **Penting:** Cloudflare Workers/Pages hanya menjalankan JavaScript/TypeScript
> (Workers runtime). Keduanya **tidak dapat** menjalankan aplikasi Python
> FastAPI, `face_recognition`/`dlib`, Pillow, atau koneksi PostgreSQL langsung.
> Karena itu backend SIDEWA tetap berjalan di origin (Colab + Cloudflare Tunnel,
> Docker, VPS, atau platform container lain). Workers/Pages meneruskan request
> ke origin tersebut.

## Arsitektur

```
Browser
  │  https://sidewa.riau.ai        (Worker, opsional)
  │  https://sidewa.pages.dev      (Pages Functions, opsional)
  ▼
Cloudflare edge (TLS, WAF, cache /static/*, header keamanan)
  ▼
Origin FastAPI  https://dprd.riau.ai  →  Cloudflare Tunnel  →  Colab :8000
  ▼
PostgreSQL lokal + media HF S3
```

Yang didapat dari deployment ini:

- Aplikasi bisa diakses lewat domain/route Cloudflare tambahan.
- Aset `/static/*` di-cache di edge (Worker).
- Endpoint diagnostik `/__edge/health` dan `/__edge/ready`.
- Redirect absolut milik origin ditulis ulang agar tetap di domain edge.
- Header keamanan tambahan (HSTS, nosniff, dst.).

Yang **tidak** bisa:

- Menjalankan pengenalan wajah, pemrosesan gambar, atau `uvicorn` di edge.
- Menghilangkan kebutuhan origin Python. Untuk itu perlu penulisan ulang
  backend (mis. Hono/TypeScript + Hyperdrive + layanan ML terpisah) dan itu
  proyek yang berbeda.

## Prasyarat

1. Origin SIDEWA sudah hidup dan bisa diakses, mis.
   `curl https://dprd.riau.ai/healthz` → `200`.
2. Akun Cloudflare dengan zona domain (mis. `riau.ai`) bila ingin custom domain.
3. Node.js 20+ dan `npx` untuk Wrangler.

```bash
npx -y wrangler@4 login
```

Untuk CI/Colab tanpa login interaktif, buat API Token di
**My Profile → API Tokens → Create Token**, gunakan template
*Edit Cloudflare Workers*, lalu tambahkan izin **Cloudflare Pages: Edit**.
Simpan sebagai environment variable:

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...   # opsional bila akun hanya satu
```

## Satu perintah (Worker + Pages)

```bash
npx -y wrangler@4 login          # sekali saja, atau set CLOUDFLARE_API_TOKEN
cd deploy/cloudflare
./deploy.sh                      # Worker + Pages
./deploy.sh worker               # Worker saja
./deploy.sh pages                # Pages saja
ORIGIN=https://origin.dprd.riau.ai ./deploy.sh
```

Atau lewat Makefile:

```bash
make cloudflare-deploy
```

## Opsi A — Cloudflare Worker (disarankan untuk domain sendiri)

```bash
cd deploy/cloudflare/worker
npm install
npx wrangler deploy
```

Hasil pertama berupa `https://sidewa-edge.<subdomain>.workers.dev`.
Uji:

```bash
curl https://sidewa-edge.<subdomain>.workers.dev/__edge/health
curl https://sidewa-edge.<subdomain>.workers.dev/healthz
```

Tambahkan custom domain lewat dashboard:

**Workers & Pages → sidewa-edge → Settings → Domains & Routes → Add custom domain**

atau aktifkan `routes` di `wrangler.toml`:

```toml
routes = [
  { pattern = "sidewa.riau.ai/*", zone_name = "riau.ai" }
]
```

> Jangan memakai hostname yang sama dengan `ORIGIN`. Bila ingin
> `dprd.riau.ai` sendiri dilayani Worker, pindahkan tunnel ke hostname lain
> (mis. `origin.dprd.riau.ai`), lalu set `ORIGIN` ke hostname baru itu.

Mengubah origin:

```bash
npx wrangler deploy --var ORIGIN:https://origin.dprd.riau.ai
```

atau edit `[vars] ORIGIN` di `wrangler.toml` / dashboard.

## Opsi B — Cloudflare Pages (proxy penuh, tanpa domain sendiri)

```bash
cd deploy/cloudflare/pages
npx wrangler pages project create sidewa-pages --production-branch main
npx wrangler pages deploy
```

Hasil: `https://sidewa-pages.pages.dev` menampilkan aplikasi SIDEWA
(seluruh request diproksikan ke origin).

Uji:

```bash
curl https://sidewa-pages.pages.dev/__edge/health
curl https://sidewa-pages.pages.dev/healthz
curl -I https://sidewa-pages.pages.dev/login
```

Atur `ORIGIN` di **Pages → Settings → Environment variables** bila origin
bukan `https://dprd.riau.ai`.

## Konfigurasi origin

Karena request dari edge memiliki `Host: dprd.riau.ai` (hostname origin),
`SIDEWA_TRUSTED_HOSTS` tidak perlu memuat domain edge. Namun bila origin
dipindah ke hostname baru, tambahkan hostname itu:

```dotenv
SIDEWA_TRUSTED_HOSTS=dprd.riau.ai,origin.dprd.riau.ai,sidewa.riau.ai,localhost,127.0.0.1
```

Cookies sesi tetap bekerja karena origin tidak menetapkan atribut `Domain`;
browser menyimpannya untuk domain edge yang sedang dibuka. Pastikan
`SIDEWA_COOKIE_SECURE=true` (default produksi) dan edge selalu HTTPS.

## Batas & kuota

| Batas | Nilai |
| --- | --- |
| Body request Workers/Pages | 100 MB (SIDEWA membatasi 15 MB/foto) |
| Request gratis | 100.000/hari per produk |
| CPU gratis | 10 ms/request (proxy didominasi I/O, bukan CPU) |
| WebSocket | Tidak dipakai SIDEWA |

Bila traffic melebihi kuota gratis, gunakan paket berbayar atau arahkan DNS
langsung ke tunnel tanpa Worker/Pages.

## Keamanan

- Worker/Pages hanya meneruskan header, bukan menyimpan kredensial.
- Header hop-by-hop dan `Host` dibuang sebelum request ke origin.
- `X-Forwarded-Proto: https` memastikan redirect HTTPS origin tidak loop.
- Redirect absolut ke origin ditulis ulang menjadi path relatif.
- `/__edge/health` dan `/__edge/ready` tidak di-cache.

## Troubleshooting

| Gejala | Penyebab umum | Solusi |
| --- | --- | --- |
| `502 Origin tidak dapat dijangkau` | Tunnel/origin mati | Cek `https://dprd.riau.ai/healthz`, status cloudflared |
| `403 Invalid host header` | `SIDEWA_TRUSTED_HOSTS` tidak memuat hostname origin | Tambahkan hostname origin |
| Login berhasil lalu kembali ke halaman login | Cookie ditolak | Pastikan edge HTTPS dan `SIDEWA_COOKIE_SECURE=true` |
| Aset lama terus muncul di Worker | Cache `/static/*` 5 menit | Tunggu TTL atau `wrangler deploy` dengan path aset baru |
| `Script exceeded CPU time` | Bukan tipikal untuk proxy | Kurangi ukuran respons/cache aset |

## Perintah Makefile

```bash
make edge-deploy    # deploy Worker
make pages-deploy   # deploy Pages
make edge-dev       # jalankan Worker lokal (wrangler dev)
```
