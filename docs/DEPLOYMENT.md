# Deploy SIDEWA

Dokumen ini menjelaskan dua jalur deploy:

1. **Produksi terkelola** — Supabase (database utama) + PostgreSQL lokal (cache)
   + Hugging Face S3 (media). Ini adalah arsitektur yang dipakai pada deployment
   saat ini.
2. **Docker Compose mandiri** — seluruh stack berjalan di satu server.

---

## 1. Produksi: Supabase + cache lokal + HF S3

### Arsitektur

```
Browser ──► FastAPI (N worker)
                │
                ├── baca/tulis cepat ──► PostgreSQL lokal (cache + sync_outbox)
                │                              │
                │                              └── worker outbox ──► Supabase (source of truth)
                │
                └── media ──► disk lokal (cache) ──► Hugging Face S3 (bucket kelaska, lewat rclone)
```

- **Supabase** adalah sumber kebenaran. Semua perubahan akhirnya tersimpan di sini.
- **PostgreSQL lokal** hanya cache operasional; boleh hilang dan dapat dipulihkan
  dengan `hydrate`.
- **HF S3** menyimpan media secara permanen. Disk lokal hanya cache; berkas yang
  hilang diunduh kembali saat diminta (*on-demand cache*).

Penulisan bersifat *local-first write-behind*: aplikasi menulis ke PostgreSQL
lokal, trigger mencatat perubahan ke `sync_outbox`, lalu worker mengirimkannya ke
Supabase secara batch. Dengan begitu koneksi dan kuota Supabase tetap hemat.

### Prasyarat

- Python 3.12+ dan PostgreSQL 16+ lokal.
- Proyek Supabase dengan **connection pooler** aktif.
- Bucket Hugging Face S3 (S3-compatible).
- Biner **rclone** ≥ 1.60 di `PATH` (atau lewat `SIDEWA_RCLONE_BINARY`).
  Media diunggah/diunduh ke HF S3 memakai rclone, bukan boto3.

### Langkah deploy

```bash
cd /content/sidewa-dprd-riau
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu isi nilai produksi
```

Pasang rclone (lewati bila image Docker dipakai — rclone sudah ada di dalamnya):

```bash
curl https://rclone.org/install.sh | sudo bash
rclone version
```

Isi variabel penting di `.env`:

```dotenv
SIDEWA_ENV=production
SIDEWA_SECRET_KEY=<64+ karakter acak>
SIDEWA_TRUSTED_HOSTS=<domain resmi atau * bila di belakang proxy dinamis>
SIDEWA_COOKIE_SECURE=true

# Cache lokal
SIDEWA_DATABASE_URL=postgresql+psycopg://sidewa:<password>@127.0.0.1:5432/sidewa

# Supabase — runtime memakai transaction pooler (6543)
SIDEWA_SUPABASE_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
# Skema/resync memakai session pooler (5432)
SIDEWA_SUPABASE_ADMIN_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require

SIDEWA_SYNC_ENABLED=true
SIDEWA_SYNC_INTERVAL=5
SIDEWA_SYNC_BATCH=200
SIDEWA_SYNC_HYDRATE_ON_EMPTY=true

SIDEWA_HF_S3_BUCKET=kelaska
SIDEWA_HF_S3_ENDPOINT=https://s3.hf.co/akj2025
SIDEWA_HF_S3_REGION=us-east-1
SIDEWA_HF_S3_ACCESS_KEY_ID=<access key>
SIDEWA_HF_S3_SECRET_ACCESS_KEY=<secret key>
SIDEWA_HF_S3_PREFIX=sidewa/media
SIDEWA_MEDIA_SYNC_ENABLED=true
SIDEWA_MEDIA_CACHE_ON_DEMAND=true

# rclone → HF S3 (remote dibuat otomatis dari SIDEWA_HF_S3_*)
SIDEWA_RCLONE_BINARY=rclone
SIDEWA_RCLONE_REMOTE=sidewahf
SIDEWA_RCLONE_TIMEOUT=300
SIDEWA_RCLONE_EXTRA_ARGS=

# Drive bersama tim Humas (folder drive/ di HF S3)
SIDEWA_DRIVE_ENABLED=true
SIDEWA_DRIVE_MAX_UPLOAD_MB=100
# Kuota Drive pribadi per pengguna (GB)
SIDEWA_DRIVE_QUOTA_GB=100
```

> Gunakan kredensial **database** Supabase (user `postgres.<ref>`), bukan
> service-role key. Service-role/anon key tidak dibutuhkan server ini.

Inisialisasi cache lokal, skema Supabase, lalu salin data:

```bash
python -m app.cli init-db
python -m app.cli resync --truncate   # lokal → Supabase (hati-hati: mengosongkan tabel remote)
```

`resync` juga mengunggah seluruh media ke HF S3. Untuk unggahan bertahap
berikutnya, worker media menanganinya otomatis.

Jalankan server:

```bash
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

`media-check` mencetak `ok: true` bila biner rclone ada dan bucket HF S3 dapat
dilist. Jika gagal, pesan `error` berisi keluaran rclone (mis. kredensial salah
atau endpoint tidak terjangkau).

`/readyz` menampilkan:

- `sync.schema_ready` — skema Supabase sudah siap.
- `sync.pending` — jumlah perubahan yang belum terkirim (idealnya 0).
- `sync.last_error` — kesalahan sinkronisasi terakhir, bila ada.
- `media_sync.pending` / `pending_deletions` — antrean media HF S3.
- `media_sync.backend` / `binary_available` — status klien rclone.

### Pemulihan cache

Jika PostgreSQL lokal hilang atau rusak:

```bash
python -m app.cli init-db
python -m app.cli hydrate --force    # Supabase → cache lokal
```

Media akan diunduh kembali dari HF S3 saat pertama kali diakses.

### Catatan operasional

- **Tidak ada seed otomatis.** Saat container mulai, aplikasi hanya menjalankan
  `init-db` (membuat tabel yang belum ada). Data production di Supabase dan HF S3
  tidak pernah diisi ulang.
- Perintah `seed`, `seed-staff`, `upgrade-portraits`, dan `resync` **diblokir
  total** saat `SIDEWA_ENV=production`. Tidak ada flag bypass.
- **Jangan** menjalankan `resync --truncate` saat ada perubahan lokal yang belum
  terkirim; jalankan `python -m app.cli sync` terlebih dahulu.
- Hanya satu worker yang memegang lock sinkronisasi (leader election via
  advisory lock PostgreSQL). Worker lain tetap melayani request dan menyiapkan
  skema.
- Lock skema memakai *transaction-level advisory lock* sehingga otomatis lepas
  saat transaksi selesai; tidak ada lock yang tertinggal di connection pool.
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

Stack: PostgreSQL 17, aplikasi FastAPI (4 worker), Nginx reverse proxy. Volume
`media_data` dan `postgres_data`.

Saat container mulai, aplikasi **hanya** menyiapkan tabel yang belum ada
(`init-db`). Tidak ada seed demo maupun `seed-staff` otomatis: data production
di Supabase dan HF S3 dibiarkan apa adanya.

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
