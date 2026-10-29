# SIDEWA — Sistem Dokumentasi Kegiatan Dewan

Aplikasi web untuk mendokumentasikan kegiatan DPRD Provinsi Riau yang diunggah oleh tim
Humas dan dicari oleh staf komisi berdasarkan **wajah**, **nama/jabatan**, maupun **lokasi**.

## Fitur utama

- Autentikasi berbasis sesi (Argon2), CSRF, RBAC (Super Admin, Administrator, Tim Humas, Staf Komisi, Pimpinan, Anggota Dewan).
- Login **Face ID** untuk anggota dewan dan **staf Humas**: daftarkan wajah sekali di halaman login, lalu masuk cukup dengan pemindaian wajah.
- **Dashboard pribadi per anggota dewan** berisi dokumentasi Humas, penampilan terverifikasi, tren kegiatan, serta sentimen pemberitaan media online.
- **Ruang kerja pribadi per staf Humas** (`/dashboard-staf/{id}`) berisi unggahan dokumentasi, draf, tren unggahan, status Face ID, direktori staf Humas, dan pintasan tugas harian.
- Pemantauan sentimen media online melalui **Tavily** dan **Gemini** oleh staf komisi/admin:
  Tavily mencari berita, Gemini menilai relevansi dan sentimen, lalu hasilnya
  dipadukan dengan leksikon sentimen Bahasa Indonesia.
- Unggah dokumentasi kegiatan: metadata, komisi terkait, lokasi, tanggal, foto; deteksi wajah otomatis.
- Pencarian berdasarkan wajah (unggah foto), nama/jabatan, kategori, komisi, lokasi, dan rentang tanggal.
- Direktori anggota + data wajah biometrik (encoding, bukan foto mentah) dengan persetujuan.
- Dashboard statistik, log audit, ekspor CSV, health/metrics, API v1 + token Bearer.
- Antarmuka bergaya fotoyu.com: sidebar ramping, aksen lavender, pill button, kartu rounded, tipografi Roboto/Quicksand.

## Tumpukan teknologi

- Backend: FastAPI, SQLAlchemy 2, Jinja2, Pillow, NumPy, dlib + `face_recognition`.
- Database: SQLite (pengembangan) / PostgreSQL (produksi).
- Frontend: HTML + CSS + JavaScript vanilla (tanpa build step).

## Arsitektur produksi: Supabase + cache lokal + HF S3

Pada mode produksi, SIDEWA memakai tiga lapisan:

| Lapisan | Peran | Teknologi |
|---|---|---|
| **Database utama** | Sumber kebenaran (source of truth) | Supabase PostgreSQL |
| **Cache lokal** | Buffer operasional + antrean outbox | PostgreSQL lokal |
| **Object storage** | Penyimpanan foto & thumbnail | Hugging Face S3 (`bucket=kelaska`) |

Alur tulis bersifat **local-first write-behind**:

1. Aplikasi membaca/menulis ke PostgreSQL lokal sehingga latensi rendah dan
   koneksi Supabase tetap sedikit.
2. Trigger PostgreSQL mencatat setiap perubahan ke tabel `sync_outbox`.
3. Worker latar belakang mengirim outbox ke Supabase secara batch (default
   tiap 5 detik, 200 baris per batch).
4. Media ditulis ke disk lokal lalu diunggah ke HF S3 oleh worker media.
   Jika cache lokal hilang, berkas diunduh kembali saat pertama kali diminta
   (*on-demand cache*).
5. Saat cache lokal kosong, data dipulihkan otomatis dari Supabase
   (`hydrate`).

Supabase tetap menjadi sumber kebenaran: semua data akhirnya tersimpan di
Supabase, sedangkan PostgreSQL lokal hanya cache yang boleh hilang.

> **Keamanan:** tabel aplikasi di Supabase memakai RLS dan akses `anon` /
> `authenticated` dicabut. Aplikasi terhubung memakai kredensial database
> (bukan service-role key). Jangan commit `.env`.

## Memulai

```bash
cd dprd-riau
python -m venv .venv && source .venv/bin/activate
make install-dev
cp .env.example .env   # sesuaikan bila perlu
make init
make seed              # data demo (opsional)
make seed-staff        # daftar + foto staf Humas resolusi penuh (idempoten)
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

Akun **Anggota Dewan** tidak dibuat manual. Akun ini terbentuk otomatis saat anggota
mendaftarkan Face ID di halaman login, lalu terhubung ke dashboard pribadinya.

Nonaktifkan demo di produksi: `SIDEWA_DEMO_MODE=false`.

## Dashboard anggota & sentimen media online

Setiap anggota dewan memiliki dashboard di `/dashboard-anggota/{id}` yang
menggabungkan dua sumber data:

1. **Publikasi & dokumentasi Humas** — kegiatan terbit yang tertaut pada anggota,
   jumlah foto, penampilan terverifikasi, tren enam bulan, dan kategori kegiatan.
2. **Sentimen pemberitaan media online** — hasil pencarian **Tavily** yang disimpan
   sebagai `media_mentions`, lalu dinilai relevansi dan sentimennya oleh **Gemini**
   dan dipadukan dengan leksikon lokal (positif/netral/negatif).

Alur pemindaian sentimen:

1. Isi `SIDEWA_TAVILY_API_KEY` pada `.env` (buat key di <https://app.tavily.com>).
2. Isi `SIDEWA_GEMINI_API_KEY` pada `.env` (buat key di <https://aistudio.google.com/apikey>).
3. Masuk sebagai staf komisi (hanya anggota di komisinya) atau admin/superadmin.
4. Buka menu **Sentimen**, pilih anggota, lalu tekan tombol pindai.
5. Hasil tersimpan dan tampil pada dashboard anggota serta halaman
   `/anggota/{id}/sentimen`.

Tanpa API key Tavily, pemindaian dinonaktifkan. Tanpa API key Gemini, pemindaian
tetap berjalan dengan analisis leksikon lokal, sehingga aplikasi tidak pernah
bergantung pada satu penyedia saja.

Gemini juga melakukan **resolusi identitas** sebelum menilai sentimen: nama
(variasi ejaan/gelar), instansi, lokasi, jabatan, rentang tahun, akun resmi.
Berita yang membahas orang lain dengan nama sama (misalnya anggota DPRD daerah
lain) ditolak. Variabel terkait: `SIDEWA_MEMBER_IDENTITY_FILE`,
`SIDEWA_SENTIMENT_YEAR_FROM`, `SIDEWA_SENTIMENT_YEAR_TO`,
`SIDEWA_GEMINI_MIN_IDENTITY_SCORE`, `SIDEWA_GEMINI_REQUIRE_IDENTITY`.

## Konfigurasi

Seluruh konfigurasi dibaca dari environment variable (lihat `.env.example`). Variabel penting:

- `SIDEWA_SECRET_KEY` — wajib diganti di produksi.
- `SIDEWA_DATABASE_URL` — cache lokal: `sqlite:///data/sidewa.db` atau
  `postgresql+psycopg://...`. Pada arsitektur Supabase, ini **bukan** database utama.
- `SIDEWA_SUPABASE_DATABASE_URL` — koneksi runtime Supabase (transaction pooler, port 6543).
- `SIDEWA_SUPABASE_ADMIN_DATABASE_URL` — koneksi skema/resync Supabase (session pooler, port 5432).
- `SIDEWA_SYNC_ENABLED` — aktifkan outbox worker ke Supabase.
- `SIDEWA_HF_S3_*` — bucket, endpoint, dan kredensial Hugging Face S3.
- `SIDEWA_MEDIA_SYNC_ENABLED` — aktifkan unggah media ke HF S3.
- `SIDEWA_FACE_DETECTOR` — `hog` (CPU) atau `cnn` (GPU, lebih akurat).
- `SIDEWA_FACE_TOLERANCE`, `SIDEWA_FACE_AUTO_TAG`, `SIDEWA_FACE_REVIEW` — ambang pencocokan.
- `SIDEWA_FACE_LOGIN_TOLERANCE` (default `0.50`) dan `SIDEWA_FACE_LOGIN_MARGIN`
  (default `0.03`) — ambang khusus login Face ID; lebih ketat daripada pencarian wajah.
- `SIDEWA_TAVILY_API_KEY` — API key Tavily untuk pemindaian sentimen.
- `SIDEWA_TAVILY_SEARCH_DEPTH` (`basic`/`advanced`), `SIDEWA_TAVILY_MAX_RESULTS`,
  `SIDEWA_TAVILY_DAYS` — parameter pencarian berita Tavily.
- `SIDEWA_GEMINI_API_KEY` — API key Gemini untuk menilai relevansi dan sentimen.
- `SIDEWA_GEMINI_MODEL` (default `gemini-3.5-flash-lite`), `SIDEWA_GEMINI_TIMEOUT`,
  `SIDEWA_GEMINI_MAX_OUTPUT_TOKENS` — model dan batas pemanggilan Gemini.
- `SIDEWA_GEMINI_REFINE_QUERY` — minta Gemini menyusun kueri Tavily yang lebih tepat.
- `SIDEWA_GEMINI_FILTER_IRRELEVANT` — buang artikel yang tidak membahas anggota.
- `SIDEWA_GEMINI_FILTER_IRRELEVANT` — buang artikel yang tidak membahas anggota.
- `SIDEWA_GEMINI_SCORE_WEIGHT` (default `0.7`) — bobot skor Gemini terhadap leksikon.
- `SIDEWA_MEMBER_IDENTITY_FILE` (default `data/member_identity.json`) — berkas JSON
  opsional berisi alias/akun resmi per ID anggota (lihat
  `docs/member_identity.example.json`).
- `SIDEWA_SENTIMENT_YEAR_FROM` (default `2024`) dan `SIDEWA_SENTIMENT_YEAR_TO`
  (default tahun berjalan + 1) — rentang tahun terbit yang masih relevan.
- `SIDEWA_GEMINI_MIN_IDENTITY_SCORE` (default `0.65`) dan
  `SIDEWA_GEMINI_REQUIRE_IDENTITY` (default `true`) — ambang resolusi identitas.
- `SIDEWA_BOOTSTRAP_ADMIN_*` — membuat superadmin saat database kosong.

## Perintah CLI

```bash
python -m app.cli init-db
python -m app.cli seed --force
python -m app.cli create-user --username nama --name "Nama" --role humas
python -m app.cli reindex [--activity ID]
python -m app.cli stats

# Sinkronisasi Supabase
python -m app.cli resync [--truncate]   # salin seluruh data lokal → Supabase
python -m app.cli hydrate [--force]     # pulihkan cache lokal dari Supabase
python -m app.cli sync [--limit N]      # kirim outbox sekarang
python -m app.cli sync-status           # status database & media sync
```

Status sinkronisasi juga tersedia di `GET /readyz` (field `sync` dan
`media_sync`).

## Pengujian

```bash
make test          # 32 pengujian
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
