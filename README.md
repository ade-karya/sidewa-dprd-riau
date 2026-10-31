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
- **Rilis & siaran pers Humas**: susun draf, tautkan ke kegiatan, terbitkan, arsipkan, dan pantau rilis terbaru langsung dari ruang kerja staf Humas (`/rilis`).
- **Drive Humas** (`/drive`): setiap pengelola konten punya ruang pribadi **100 GB** di HF S3 (unggah banyak berkas, folder, cari, ubah nama, unduh, hapus) plus area **Drive tim** bersama di `/drive/tim`.
- Pencarian berdasarkan wajah (unggah foto), nama/jabatan, kategori, komisi, lokasi, dan rentang tanggal.
- Direktori anggota + data wajah biometrik (encoding, bukan foto mentah) dengan persetujuan.
- Dashboard statistik, log audit, ekspor CSV, health/metrics, API v1 + token Bearer.
- Antarmuka bergaya fotoyu.com: sidebar ramping, aksen lavender, pill button, kartu rounded, tipografi Roboto/Quicksand.
- **Panduan visual**: tombol **Kenali SIDEWA** di halaman login untuk presentasi aplikasi, serta **Asisten SIDEWA** yang tersedia di seluruh halaman setelah masuk. Asisten menyorot bilah atas, ikon fitur, isi halaman, dan sidebar sambil menjelaskan setiap bagian; di ponsel panel panduan tampil sebagai bottom sheet.

## Tumpukan teknologi

- Backend: FastAPI, SQLAlchemy 2, Jinja2, Pillow, NumPy, dlib + `face_recognition`.
- Database: SQLite (pengembangan) / Supabase PostgreSQL (produksi).
- Object storage: Hugging Face S3 diakses langsung lewat `boto3` (S3 native, path-style).
- Frontend: HTML + CSS + JavaScript vanilla (tanpa build step).

## Arsitektur produksi: Supabase + HF S3 langsung

Pada mode produksi, SIDEWA memakai dua layanan terkelola:

| Lapisan | Peran | Teknologi |
|---|---|---|
| **Database** | Sumber kebenaran (source of truth) | Supabase PostgreSQL (transaction pooler) |
| **Object storage** | Foto, thumbnail, dan Drive | Hugging Face S3 (`bucket=kelaska`) via `boto3` |

- Aplikasi membaca/menulis **langsung ke Supabase** melalui transaction pooler
  (port 6543). Tidak ada PostgreSQL lokal maupun worker outbox.
- Media ditulis ke disk lokal sebagai cache lalu diunggah langsung ke HF S3 oleh
  worker media (`boto3`). Jika cache lokal hilang, berkas diunduh kembali saat
  pertama kali diminta (*on-demand cache*).
- Drive memakai S3 langsung: daftar, unggah, unduh, ubah nama, hapus, pencarian,
  dan *presigned URL*.
- Tidak ada biner eksternal (`rclone`) dan tidak ada konfigurasi remote terpisah;
  endpoint serta kredensial dibaca dari `SIDEWA_HF_S3_*`.

> **Keamanan:** tabel aplikasi di Supabase memakai RLS dan akses `anon` /
> `authenticated` dicabut. Aplikasi terhubung memakai kredensial database
> (bukan service-role key). Jangan commit `.env`.

## Memulai

Tidak ada prasyarat biner tambahan. Klien S3 (`boto3`) dan PostgreSQL
(`psycopg`) dipasang otomatis dari `requirements.txt`.

```bash
cd dprd-riau
python -m venv .venv && source .venv/bin/activate
make install-dev
cp .env.example .env   # sesuaikan bila perlu
make init
make seed              # data demo (hanya development, tidak untuk production)
make seed-staff        # daftar + foto staf Humas (hanya development)
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

## Drive Humas

Setiap pengelola konten (superadmin, admin, humas, staf Humas) punya **Drive
pribadi** di `/drive` dengan kuota **100 GB** (`SIDEWA_DRIVE_QUOTA_GB`). Berkas
disimpan di `<SIDEWA_HF_S3_PREFIX>/drive/pribadi/<id pengguna>/` pada bucket HF S3
dan diakses langsung lewat `boto3` — tidak ada metadata tambahan di database.

- Unggah **beberapa berkas sekaligus**, buat folder, cari, ubah nama, unduh, dan
  hapus (berkas maupun folder beserta isinya).
- **Kuota ditegakkan saat unggah**: berkas yang melebihi sisa ruang ditolak dengan
  pesan sisa kuota, dan halaman menampilkan bilah pemakaian (peringatan pada 90%).
- Nama berkas duplikat otomatis diberi akhiran ` (2)`, ` (3)`, dan seterusnya.
- **Unduhan langsung**: tombol **Unduh** mengalihkan browser ke *presigned URL*
  HF S3 (berlaku 30 menit), jadi berkas diambil langsung dari CDN tanpa melewati
  server aplikasi. Berkas HTML/SVG/teks tetap dialirkan lewat server sebagai
  lampiran agar tidak dirender inline oleh browser.
- **Pratinjau foto**: berkas gambar (JPEG, PNG, WebP, GIF, BMP, AVIF) tampil
  sebagai thumbnail dan dapat diperbesar; aliran pratinjau tetap lewat server
  agar sesuai CSP `img-src 'self'`. SVG sengaja tidak dipratinjau demi keamanan.
- Batas ukuran per berkas diatur `SIDEWA_DRIVE_MAX_UPLOAD_MB` (default **90 MB**,
  di bawah batas 100 MB Cloudflare). Banyak berkas sekaligus diunggah satu per
  satu dari browser sehingga tiap permintaan tetap kecil dan tidak kena
  `413 Payload Too Large`.
- S3 tidak menyimpan folder kosong; aplikasi menaruh penanda `.keep` agar folder
  baru tetap tampil.
- **Drive tim** di `/drive/tim` menyimpan berkas bersama. Isi lama tetap di
  tempatnya (akar `drive/`), sedangkan folder `pribadi/` disembunyikan dari
  tampilan dan pencarian tim.
- Superadmin dan admin dapat membuka Drive staf lain lewat pemilih **Lihat Drive
  staf** untuk keperluan audit; humas/staf Humas hanya melihat Drive sendiri.
- Semua tindakan tercatat di log audit (`DRIVE_UPLOAD`, `DRIVE_FOLDER`,
  `DRIVE_RENAME`, `DRIVE_DELETE`). Staf komisi tidak memiliki akses ke Drive.

Nonaktifkan halaman ini dengan `SIDEWA_DRIVE_ENABLED=false` bila tidak diperlukan.

## Seleksi foto AI Humas

Pengelola konten Humas dapat membuka **Seleksi Foto** (`/seleksi-foto`) untuk
mengurasi puluhan foto menjadi pilihan terbaik sebelum diterapkan ke kegiatan.
Fitur ini memakai **kunci API Gemini milik masing-masing pengguna**, bukan kunci
global `SIDEWA_GEMINI_API_KEY`.

Alur kerja:

1. Pengguna membuka `/seleksi-foto`, menempelkan kunci dari
   <https://aistudio.google.com/apikey>, lalu mengisi batas **RPM/TPM/RPD**
   kunci tersebut. Default mengikuti kuota Gemini 3.5 Flash Lite untuk model
   teks: **15 RPM · 250K TPM · 500 RPD**.
2. Pilih **skill** kurasi bawaan atau buat skill sendiri sesuai preferensi tim.
3. Unggah hingga `SIDEWA_PHOTO_SELECTION_MAX_PHOTOS` foto (maks.
   `SIDEWA_MAX_UPLOAD_MB` per berkas), atur target dan ambang skor, lalu
   jalankan agen. Berkas disimpan di penyimpanan objek HF S3; batas MB hanya
   validasi berkas, bukan batas jumlah foto yang boleh diunggah.
4. Foto duplikat disaring lebih dulu dengan perceptual hash lokal—tanpa memakai
   kuota. Foto unik dinilai satu per satu dengan model
   `SIDEWA_PHOTO_SELECTION_MODEL` (default `gemini-3.5-flash-lite`). Jumlah foto
   yang diproses dibatasi kuota API, bukan kapasitas unggah.
5. Tinjau hasil, ubah pilihan bila perlu, lalu terapkan ke kegiatan atau unduh ZIP.

Agen menunggu otomatis saat batas RPM tercapai dan menjeda sesi ketika RPD habis.
Sesi dapat dilanjutkan setelah kuota direset. Kunci disimpan terenkripsi dengan
`SIDEWA_SECRET_KEY`, tidak pernah ditampilkan kembali, dan hanya dipakai untuk
fitur ini.

**Skill adaptif.** Saat opsi *Perbarui skill otomatis* aktif, agen belajar dari
foto yang benar-benar Anda terapkan dan koreksi pilihan manual. Ia menyesuaikan
ringkasan preferensi, ambang skor, dan target skill tanpa memanggil Gemini
sehingga tidak memakai kuota. Preferensi hasil belajar dapat disunting atau
dikosongkan dari halaman pengaturan, dan tombol **Selaraskan sekarang** menghitung
ulang dari riwayat koreksi.

**Berbagi skill.** Skill milik anggota Humas lain dapat dipakai langsung atau
disalin ke daftar skill pribadi. Aktifkan *Bagikan ke anggota Humas lain* pada
skill Anda untuk memunculkannya di bagian **Skill komunitas Humas**. Daftar
komunitas diurutkan berdasarkan skill yang paling banyak dipakai anggota lain
(`share_usage_count`), sehingga preset tim yang terbukti berguna muncul lebih
dulu. Menyalin skill membuat salinan pribadi yang dapat disunting dan dilatih
ulang tanpa mengubah skill milik pembuatnya.

Variabel terkait: `SIDEWA_PHOTO_SELECTION_ENABLED`,
`SIDEWA_PHOTO_SELECTION_MODEL`, `SIDEWA_PHOTO_SELECTION_RPM`,
`SIDEWA_PHOTO_SELECTION_TPM`, `SIDEWA_PHOTO_SELECTION_RPD`,
`SIDEWA_PHOTO_SELECTION_MAX_PHOTOS`, `SIDEWA_PHOTO_SELECTION_WORKERS`,
`SIDEWA_PHOTO_SELECTION_TIMEOUT`, dan
`SIDEWA_PHOTO_SELECTION_SYNC` (khusus pengujian).

## Konfigurasi

Seluruh konfigurasi dibaca dari environment variable (lihat `.env.example`). Variabel penting:

- `SIDEWA_SECRET_KEY` — wajib diganti di produksi.
- `SIDEWA_DATABASE_URL` — koneksi database. Mode produksi langsung ke Supabase
  transaction pooler: `postgresql+psycopg://...pooler.supabase.com:6543/postgres?sslmode=require`.
  Pengembangan dapat memakai `sqlite:///data/sidewa.db`.
- `SIDEWA_SUPABASE_DATABASE_URL` — koneksi runtime Supabase (transaction pooler, port 6543).
- `SIDEWA_SUPABASE_ADMIN_DATABASE_URL` — koneksi skema/resync Supabase (session pooler, port 5432).
- `SIDEWA_SYNC_ENABLED` — worker outbox lama; biarkan `false` pada mode langsung Supabase.
- `SIDEWA_HF_S3_*` — bucket, endpoint, dan kredensial Hugging Face S3.
- `SIDEWA_MEDIA_SYNC_ENABLED` — aktifkan worker unggah media ke HF S3.
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
- `SIDEWA_GEMINI_LIVE_ENABLED` — aktifkan Asisten SIDEWA berbasis Gemini Live.
- `SIDEWA_GEMINI_LIVE_MODEL` (default `gemini-3.8-live`) — model Live untuk
  percakapan panduan umum.
- `SIDEWA_GEMINI_LIVE_TECHNICAL_MODEL` (default
  `gemini-3.8-live-extended-thinking`) — model Gemini 3.8 Live Extended Thinking
  untuk pertanyaan teknis.
- `SIDEWA_GEMINI_LIVE_THINKING_LEVEL` (default `low`) — tingkat penalaran model
  extended thinking; `SIDEWA_GEMINI_LIVE_VOICE` (default `Aoede`) — suara narasi.
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
python -m app.cli seed --force   # HAPUS semua data; diblokir di production
python -m app.cli create-user --username nama --name "Nama" --role humas
python -m app.cli reindex [--activity ID]
python -m app.cli stats

# Sinkronisasi Supabase (hanya mode cache lokal)
python -m app.cli resync [--truncate]   # salin seluruh data lokal → Supabase
python -m app.cli hydrate [--force]     # pulihkan cache lokal dari Supabase
python -m app.cli sync [--limit N]      # kirim outbox sekarang
python -m app.cli sync-status           # status database & media sync
python -m app.cli media-check           # uji koneksi langsung ke HF S3
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
