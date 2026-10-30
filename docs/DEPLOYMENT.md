# Deploy SIDEWA

Dokumen ini menjelaskan dua jalur deploy:

1. **Produksi terkelola** — Supabase (database) + Hugging Face S3 (media),
   keduanya diakses langsung. Ini adalah arsitektur yang dipakai pada deployment
   saat ini.
2. **Docker Compose mandiri** — seluruh stack berjalan di satu server.

---

## 1. Produksi: Supabase + HF S3 langsung

### Arsitektur

```
Browser ──► FastAPI (N worker)
                │
                ├── baca/tulis langsung ──► Supabase PostgreSQL (source of truth)
                │
                └── media ──► disk lokal (cache) ──► Hugging Face S3 (bucket kelaska, via boto3)
```

- **Supabase** adalah sumber kebenaran. Aplikasi terhubung langsung melalui
  transaction pooler (port 6543); tidak ada PostgreSQL lokal maupun worker outbox.
- **HF S3** menyimpan media dan Drive secara permanen. Disk lokal hanya cache;
  berkas yang hilang diunduh kembali saat diminta (*on-demand cache*).
- **Tidak ada rclone.** Semua operasi S3 memakai `boto3` dengan *path-style
  addressing* dan signature v4.

### Prasyarat

- Python 3.12+.
- Proyek Supabase dengan **connection pooler** aktif.
- Bucket Hugging Face S3 (S3-compatible) beserta access key/secret.
- Tidak ada biner tambahan; `boto3` dan `psycopg` terpasang dari
  `requirements.txt`.

### Langkah deploy

```bash
cd /content/sidewa-dprd-riau
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu isi nilai produksi
```

Isi variabel penting di `.env`:

```dotenv
SIDEWA_ENV=production
SIDEWA_SECRET_KEY=<64+ karakter acak>
SIDEWA_TRUSTED_HOSTS=<domain resmi atau * bila di belakang proxy dinamis>
SIDEWA_COOKIE_SECURE=true

# Database langsung ke Supabase (transaction pooler, port 6543)
SIDEWA_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
SIDEWA_SUPABASE_DATABASE_URL=<sama dengan SIDEWA_DATABASE_URL>
# Skema/resync memakai session pooler (5432)
SIDEWA_SUPABASE_ADMIN_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require

# Mode langsung Supabase: worker outbox tidak dipakai.
SIDEWA_SYNC_ENABLED=false
SIDEWA_SYNC_HYDRATE_ON_EMPTY=false

SIDEWA_HF_S3_BUCKET=kelaska
SIDEWA_HF_S3_ENDPOINT=https://s3.hf.co/akj2025
SIDEWA_HF_S3_REGION=us-east-1
SIDEWA_HF_S3_ACCESS_KEY_ID=<access key>
SIDEWA_HF_S3_SECRET_ACCESS_KEY=<secret key>
SIDEWA_HF_S3_PREFIX=sidewa/media
SIDEWA_MEDIA_SYNC_ENABLED=true
SIDEWA_MEDIA_CACHE_ON_DEMAND=true

# Drive bersama tim Humas (folder drive/ di HF S3)
SIDEWA_DRIVE_ENABLED=true
# Bucket publik untuk Drive (kosong = ikut SIDEWA_HF_S3_BUCKET).
SIDEWA_DRIVE_BUCKET=sidewa-production
# Maksimal per berkas; jangan melebihi 100 MB (batas body Cloudflare).
SIDEWA_DRIVE_MAX_UPLOAD_MB=90
# Kuota Drive pribadi per pengguna (GB)
SIDEWA_DRIVE_QUOTA_GB=100
```

> Unduhan Drive dialihkan ke *presigned URL* HF S3 (berlaku 30 menit) sehingga
> lalu lintas berkas besar tidak melewati server ini. Pastikan domain
> `s3.hf.co` dan CDN Hugging Face dapat diakses dari jaringan pengguna.

> Gunakan kredensial **database** Supabase (user `postgres.<ref>`), bukan
> service-role key. Service-role/anon key tidak dibutuhkan server ini.

Siapkan tabel yang belum ada, lalu jalankan server:

```bash
python -m app.cli init-db
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers
```

Gunakan systemd/supervisor agar proses tetap hidup, dan Nginx di depan untuk TLS.

### Verifikasi

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/readyz | python -m json.tool
python -m app.cli sync-status
python -m app.cli media-check
```

`media-check` mencetak `ok: true` bila bucket HF S3 dapat dilist lewat boto3.
Jika gagal, pesan `error` berisi kode/keterangan dari S3 (mis. kredensial salah
atau endpoint tidak terjangkau).

`/readyz` menampilkan:

- `database` — status koneksi langsung ke Supabase.
- `media_sync.pending` / `pending_deletions` — antrean media HF S3.
- `media_sync.backend` — `boto3` bila worker media aktif.

### Catatan operasional

- **Tidak ada seed otomatis.** Saat container mulai, aplikasi hanya menjalankan
  `init-db` (membuat tabel yang belum ada). Data production di Supabase dan HF S3
  tidak pernah diisi ulang.
- Perintah `seed`, `seed-staff`, `upgrade-portraits`, dan `resync` **diblokir
  total** saat `SIDEWA_ENV=production`. Tidak ada flag bypass.
- Media diunggah oleh worker latar belakang (`SIDEWA_MEDIA_SYNC_INTERVAL`,
  default 30 detik). Setiap berkas baru dicatat di antrean `media_sync` lalu
  diunggah langsung ke HF S3.
- RLS di Supabase aktif dan akses `anon`/`authenticated` dicabut. Aplikasi
  terhubung sebagai user database.
- Backup: Supabase menangani backup database; media ada di HF S3. Simpan `.env`
  di tempat aman dan jangan commit.

### Migrasi potret lama ke resolusi penuh

Instalasi lama menyimpan path thumbnail (`*_thumb.jpg`) sebagai potret. Setelah
pembaruan, jalankan sekali (idempoten) agar potret memakai gambar utama:

```bash
python -m app.cli upgrade-portraits --dry-run   # ringkasan tanpa mengubah data
python -m app.cli upgrade-portraits             # terapkan + unggah ke HF S3
```

Perintah ini memakai kembali gambar utama yang sudah ada (misalnya dari data
wajah anggota) lalu membuat thumbnail pendamping; foto staf dibuat ulang dari
`seed_assets/staff_portraits/`. Berkas lama tidak dihapus.

---

## 2. Docker Compose mandiri

```bash
cp .env.example .env
# Isi POSTGRES_PASSWORD, SIDEWA_SECRET_KEY, SIDEWA_TRUSTED_HOSTS
docker compose up -d --build
```

Stack: PostgreSQL 17 (container `db`), aplikasi FastAPI (4 worker), Nginx reverse
proxy. Volume `media_data` dan `postgres_data`.

Jalur ini **self-hosted**: database ada di container `db`, bukan di Supabase.
Media tetap dikirim langsung ke Hugging Face S3 lewat `boto3` (tidak ada
rclone). Bila ingin memakai Supabase langsung lewat Compose, hapus baris
`SIDEWA_DATABASE_URL` pada `docker-compose.yml` sehingga nilai dari `.env`
(transaction pooler port 6543) yang dipakai.

Saat container mulai, aplikasi **hanya** menyiapkan tabel yang belum ada
(`init-db`). Tidak ada seed demo maupun `seed-staff` otomatis: data production
di database dan HF S3 dibiarkan apa adanya.

Untuk pengembangan non-produksi, isi data demo secara manual:

```bash
SIDEWA_ENV=development python -m app.cli seed --force
SIDEWA_ENV=development python -m app.cli seed-staff
```

## Produksi tanpa Docker (stack mandiri)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit
python -m app.cli init-db
# Seed/seed-staff/resync sengaja tidak dijalankan di production.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
```

Gunakan supervisor/systemd untuk menjaga proses. Letakkan Nginx di depan untuk
TLS dan rate limit.

## Backup (stack mandiri)

- Database: `pg_dump` (PostgreSQL) atau salin file SQLite saat aplikasi berhenti.
- Media: arsipkan direktori `SIDEWA_MEDIA_ROOT`.
- Simpan `.env` di tempat aman.
