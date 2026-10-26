# SIDEWA — Sistem Dokumentasi Kegiatan Dewan

Aplikasi web untuk mendokumentasikan kegiatan DPRD Provinsi Riau yang diunggah oleh tim
Humas dan dicari oleh staf komisi berdasarkan **wajah**, **nama/jabatan**, maupun **lokasi**.

## Fitur utama

- Autentikasi berbasis sesi (Argon2), CSRF, RBAC (Super Admin, Administrator, Tim Humas, Staf Komisi, Pimpinan).
- Unggah dokumentasi kegiatan: metadata, komisi terkait, lokasi, tanggal, foto; deteksi wajah otomatis.
- Pencarian berdasarkan wajah (unggah foto), nama/jabatan, kategori, komisi, lokasi, dan rentang tanggal.
- Direktori anggota + data wajah biometrik (encoding, bukan foto mentah) dengan persetujuan.
- Dashboard statistik, log audit, ekspor CSV, health/metrics, API v1 + token Bearer.
- Antarmuka bergaya fotoyu.com: sidebar ramping, aksen lavender, pill button, kartu rounded, tipografi Roboto/Quicksand.

## Tumpukan teknologi

- Backend: FastAPI, SQLAlchemy 2, Jinja2, Pillow, NumPy, dlib + `face_recognition`.
- Database: SQLite (pengembangan) / PostgreSQL (produksi).
- Frontend: HTML + CSS + JavaScript vanilla (tanpa build step).

## Memulai

```bash
cd dprd-riau
python -m venv .venv && source .venv/bin/activate
make install-dev
cp .env.example .env   # sesuaikan bila perlu
make init
make seed              # data demo (opsional)
make run               # http://127.0.0.1:8000
```

Akun demo (mode demo aktif):

| Pengguna | Kata sandi | Peran |
|---|---|---|
| superadmin | `Riau#Admin2026` | Super Admin |
| admin | `Admin#Riau2026` | Administrator |
| humas | `Humas#Riau2026` | Tim Humas |
| komisi1 … komisi5 | `KomisiN#Riau2026` | Staf Komisi |
| pimpinan | `Pimpinan#Riau2026` | Pimpinan |

Nonaktifkan demo di produksi: `SIDEWA_DEMO_MODE=false`.

## Konfigurasi

Seluruh konfigurasi dibaca dari environment variable (lihat `.env.example`). Variabel penting:

- `SIDEWA_SECRET_KEY` — wajib diganti di produksi.
- `SIDEWA_DATABASE_URL` — `sqlite:///data/sidewa.db` atau `postgresql+psycopg://...`.
- `SIDEWA_FACE_DETECTOR` — `hog` (CPU) atau `cnn` (GPU, lebih akurat).
- `SIDEWA_FACE_TOLERANCE`, `SIDEWA_FACE_AUTO_TAG`, `SIDEWA_FACE_REVIEW` — ambang pencocokan.
- `SIDEWA_BOOTSTRAP_ADMIN_*` — membuat superadmin saat database kosong.

## Perintah CLI

```bash
python -m app.cli init-db
python -m app.cli seed --force
python -m app.cli create-user --username nama --name "Nama" --role humas
python -m app.cli reindex [--activity ID]
python -m app.cli stats
```

## Pengujian

```bash
make test          # 14 pengujian
make cov           # dengan cakupan
make lint          # ruff
```

## Deploy

Lihat `docs/DEPLOYMENT.md` (Docker Compose + PostgreSQL + Nginx) dan `deploy/Dockerfile`.

## Dokumentasi

- `docs/API.md` — endpoint REST v1 dan autentikasi.
- `docs/SECURITY.md` — model keamanan.
- `docs/USER_GUIDE.md` — panduan pengguna.

## Catatan mesin wajah

Paket `face_recognition` berasal dari repositori induk (`/content/face_recognition`). Pada instalasi mandiri, dependensi `face-recognition==1.3.0` dipasang melalui `requirements.txt`. `face_engine` menambahkan akar repositori induk ke `sys.path` bila tersedia, sehingga pengembangan dapat memakai pustaka lokal.
