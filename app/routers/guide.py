"""Asisten presentasi SIDEWA berbasis Gemini Live API.

Browser tidak pernah menerima API key. Halaman panduan membuka WebSocket ke
``/panduan/live``; router ini menjadi jembatan audio/tulisan dua arah ke Gemini
Live. Pertanyaan teknis otomatis diarahkan ke Gemini 3.8 Live Extended Thinking,
sedangkan pertanyaan presentasi biasa memakai Gemini 3.8 Live standar.

Dua sesi Live dipelihara terpisah agar perpindahan model tidak memutus percakapan
atau memaksa pengguna menunggu koneksi baru. Keduanya memakai pengetahuan aplikasi
yang sama dan ringkasan data terkini, sehingga jawaban tetap konsisten.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func

from ..config import settings
from ..constants import ROLE_ANGGOTA, ROLE_LABELS, ROLE_STAF
from ..database import SessionLocal
from ..models import (
    Activity,
    ActivityPhoto,
    Commission,
    MediaMention,
    Member,
    SentimentRun,
    User,
)

try:  # websockets >= 13
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # pragma: no cover - fallback untuk versi lama
    from websockets.client import connect as ws_connect  # type: ignore

logger = logging.getLogger("sidewa.guide")

router = APIRouter()

STANDARD = "standard"
TECHNICAL = "technical"

MAX_VOICE_CHUNKS = 240  # sekitar 60 detik audio 16 kHz
VOICE_CLASSIFY_DELAY = 0.45
CONNECT_TIMEOUT = 25

# Kata kunci yang menandakan pertanyaan teknis. Pemilihan model dilakukan di
# server agar pengguna tidak perlu memilih mode secara manual saat presentasi.
_TECHNICAL_TERMS = {
    "api",
    "endpoint",
    "rest",
    "json",
    "http",
    "https",
    "websocket",
    "ws",
    "wss",
    "backend",
    "frontend",
    "fullstack",
    "framework",
    "fastapi",
    "uvicorn",
    "asgi",
    "wsgi",
    "python",
    "javascript",
    "typescript",
    "html",
    "css",
    "jinja",
    "sql",
    "nosql",
    "database",
    "db",
    "postgres",
    "postgresql",
    "supabase",
    "sqlite",
    "tabel",
    "skema",
    "schema",
    "migrasi",
    "migration",
    "query",
    "indeks",
    "index",
    "relasi",
    "foreign key",
    "transaction",
    "server",
    "deploy",
    "deployment",
    "docker",
    "container",
    "nginx",
    "proxy",
    "load balancer",
    "scaling",
    "kapasitas",
    "latency",
    "uptime",
    "infrastruktur",
    "arsitektur",
    "architecture",
    "sinkronisasi",
    "sync",
    "outbox",
    "worker",
    "antrean",
    "queue",
    "cron",
    "cache",
    "caching",
    "storage",
    "object storage",
    "s3",
    "bucket",
    "cdn",
    "backup",
    "restore",
    "disaster recovery",
    "keamanan",
    "security",
    "privasi",
    "enkripsi",
    "encryption",
    "hash",
    "argon",
    "argon2",
    "csrf",
    "xss",
    "csp",
    "rbac",
    "autentikasi",
    "authentication",
    "otorisasi",
    "authorization",
    "session",
    "cookie",
    "token",
    "jwt",
    "oauth",
    "sso",
    "sertifikat",
    "ssl",
    "tls",
    "domain",
    "dns",
    "firewall",
    "rate limit",
    "audit log",
    "logging",
    "monitoring",
    "metrics",
    "healthz",
    "readyz",
    "observability",
    "error",
    "bug",
    "debug",
    "testing",
    "unit test",
    "kode",
    "source code",
    "repository",
    "repo",
    "git",
    "ci/cd",
    "pipeline",
    "environment",
    "env",
    "konfigurasi",
    "configuration",
    "variabel",
    "config",
    "face recognition",
    "face_recognition",
    "dlib",
    "opencv",
    "numpy",
    "pillow",
    "encoding",
    "embedding",
    "biometrik",
    "algoritma",
    "model ai",
    "gemini",
    "tavily",
    "llm",
    "prompt",
    "machine learning",
    "computer vision",
    "deteksi wajah",
    "tolerance",
    "toleransi",
    "threshold",
    "ambang",
    "pixel",
    "resolusi",
    "exif",
    "thumbnail",
    "unggah",
    "upload",
    "multipart",
    "streaming",
    "pcm",
    "audio",
    "codec",
    "webhook",
    "integrasi",
    "integration",
    "sdk",
    "library",
    "dependensi",
    "dependency",
    "open source",
    "lisensi",
    "maintenance",
    "pemeliharaan",
    "troubleshooting",
    "ukuran maksimal",
    "batas ukuran",
    "batas unggah",
    "limit unggah",
    "ukuran file",
    "kapasitas penyimpanan",
    "waktu proses",
}

_TECHNICAL_PATTERNS = (
    r"\bdi balik layar\b",
    r"\bcara kerja sistem(nya)?\b",
    r"\bsecara teknis\b",
    r"\bteknis\b",
    r"\bteknologi(nya)?\b",
    r"\bstack\b",
    r"\bspesifikasi\b",
    r"\bberapa (mb|gb|tb|detik|ms|baris|pixel)\b",
    r"\bberapa (ukuran|batas|limit)\b",
    r"\bberapa lama proses\b",
    r"\bberapa banyak (data|baris|foto|tabel)\b",
    r"\bdi mana (data|foto|file) disimpan\b",
    r"\bbagaimana (data|foto|file) (disimpan|diamankan|diproses)\b",
    r"\bapa yang terjadi (jika|bila) (server|database|koneksi)\b",
    r"\bapakah (data|aplikasi|sistem) (aman|terenkripsi|terbackup)\b",
    r"\bsiapa (yang|pengembang|tim) (membuat|mengembangkan|merawat)\b",
)

_TECHNICAL_RE = re.compile("|".join(_TECHNICAL_PATTERNS), re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)


def is_technical_question(text: str) -> bool:
    """Deteksi pertanyaan teknis tanpa memanggil model tambahan (tanpa latensi)."""
    value = (text or "").strip().lower()
    if len(value) < 4:
        return False
    if _TECHNICAL_RE.search(value):
        return True
    words = set(_WORD_RE.findall(value))
    if words & _TECHNICAL_TERMS:
        return True
    # Frase multi-kata pada daftar istilah.
    return any(term in value for term in _TECHNICAL_TERMS if " " in term)


APP_KNOWLEDGE = """
### PROFIL APLIKASI
- Nama: SIDEWA — Sistem Dokumentasi Kegiatan Dewan.
- Organisasi: DPRD Provinsi Riau.
- Tujuan: menyatukan arsip dokumentasi kegiatan dewan, mempercepat penemuan
  dokumentasi lewat wajah/nama/jabatan/komisi/lokasi/tanggal, serta menyajikan
  statistik kegiatan dan sentimen pemberitaan media online.
- Pengguna: Pimpinan, Anggota Dewan, Tim Humas, Staf Komisi, Administrator, dan
  Super Admin. Sebagian pengguna adalah anggota dewan yang tidak mendalami
  teknologi; jawaban presentasi harus tetap sederhana.

### MASALAH YANG DISELESAIKAN
- Foto dan dokumentasi tersebar di ponsel, grup pesan, dan folder pribadi.
- Pencarian dokumentasi manual lambat dan bergantung pada ingatan orang.
- Rekap kehadiran/penampilan anggota di kegiatan memakan waktu.
- Isu dan pemberitaan media sulit dipantau secara sistematis.
- Akses data tidak seragam antar peran; arsip mudah hilang atau ganda.
- Bukti kegiatan sulit disajikan cepat saat rapat atau permintaan pimpinan.

### HALAMAN DAN ALUR UTAMA
- `/` Dasbor: ringkasan statistik, dokumentasi terbaru, aktivitas, dan (untuk
  admin) audit terakhir.
- `/cari` Pencarian: pencarian teks (nama, jabatan, kategori, lokasi, tanggal)
  dan pencarian wajah dengan unggah foto.
- `/kegiatan` Daftar dokumentasi; `/kegiatan/baru` unggah baru; detail kegiatan
  berisi metadata, galeri foto, anggota tertaut, dan hasil deteksi wajah.
- Aksi kegiatan: sunting, terbitkan, arsipkan, pulihkan, hapus, unggah foto,
  proses ulang wajah, tautkan/lepas anggota, konfirmasi/tolak deteksi, ekspor CSV.
- `/anggota` Direktori anggota; detail berisi jabatan, komisi, dapil, partai,
  kontak, bio, data wajah, dan Face ID login. Admin dapat menonaktifkan anggota
  atau menghapus data Face ID.
- `/komisi` Daftar komisi dan anggotanya; detail komisi memuat anggota, dokumentasi,
  staf, dan formulir penyuntingan bagi admin.
- `/dashboard-anggota/{id}` Dasbor pribadi anggota: dokumentasi Humas, penampilan
  terverifikasi, tren enam bulan, kategori kegiatan, tugas & fungsi, sentimen.
- `/dashboard-staf` dan `/dashboard-staf/{id}` Ruang kerja staf Humas: pintasan,
  draf, rilis, statistik publikasi, tren unggahan, dan status Face ID.
- `/staf-humas` Direktori staf Humas beserta jabatan, unggahan, dan status Face ID.
- `/seleksi-foto` Kurasi foto berbantuan AI: unggah, penilaian kualitas, pemilihan
  foto terbaik, lalu penerapan ke kegiatan.
- `/rilis/baru` Tulis rilis Humas. Unggahan rekaman audio disimpan lebih dulu ke
  Drive pribadi (`Rilis/Audio`), lalu Gemini 3.8 Flash menyusun judul, ringkasan,
  isi 5W1H, tag, tanggal, dan kegiatan terkait.
- `/rilis/skill` Skill bersama *Gaya Rilis Humas*: satu panduan gaya untuk semua
  pengguna yang diperbarui otomatis dari rilis yang sedang terbit.
- `/drive` Penyimpanan berkas Humas di HF S3: unggah, cari, ubah nama, unduh,
  pratinjau foto (JPEG/PNG/WebP/GIF/BMP/AVIF), dan kelola folder pribadi maupun
  tim. Pratinjau SVG dinonaktifkan demi keamanan.
- `/sentimen` dan `/anggota/{id}/sentimen`: pemindaian serta riwayat pemberitaan.
- `/pengguna` (admin) kelola akun, peran, komisi, status, reset kata sandi.
- `/audit` log audit dan ekspor CSV; `/profil` profil, ganti sandi, token API.
- `/healthz`, `/readyz`, `/metrics` untuk pemantauan operasional.
- `/panduan/live` WebSocket asisten presentasi (Gemini Live).

### PERAN DAN HAK AKSES
- Super Admin: akses penuh, konfigurasi sistem, pengguna, anggota, konten, audit.
- Administrator: mengelola konten, anggota, komisi, pengguna, audit, dan token API.
- Tim Humas: membuat/menyunting/menerbitkan/mengarsipkan dokumentasi, mengunggah
  foto, meninjau deteksi wajah, dan menautkan anggota.
- Staf Komisi: mencari dan membaca dokumentasi, serta memindai sentimen anggota
  di komisinya sendiri. Tidak dapat mengubah konten atau pengguna.
- Pimpinan: melihat seluruh dokumentasi, statistik, dashboard anggota, dan laporan
  (terutama read-only).
- Anggota Dewan: akun dibuat otomatis saat pendaftaran Face ID; hanya dapat membuka
  dasbor pribadinya, dokumentasi Humas tentang dirinya, dan sentimen publiknya.
- Semua akses media privat diperiksa terhadap visibilitas kegiatan dan peran.

### FITUR RINCI
1. Dokumentasi kegiatan
   - Metadata: judul, kategori, tanggal, lokasi, komisi terkait, deskripsi.
   - Kategori: Rapat Paripurna, Rapat Kerja, Rapat Dengar Pendapat, Kunjungan
     Kerja, Reses, Sosialisasi, Monitoring, Pelantikan, Lainnya.
   - Status: draf, terbit, diarsipkan. Hanya kegiatan terbit yang tampil ke
     pengguna umum/staf; draf dan arsip dibatasi.
   - Maksimal 12 foto per kegiatan, 15 MB per foto, 40 megapiksel per gambar.
     Foto dibuat thumbnail; metadata EXIF dibersihkan saat normalisasi.
2. Deteksi dan pencarian wajah
   - Saat foto diunggah, sistem mendeteksi wajah dan mencocokkan encoding dengan
     data anggota. Hasil otomatis di atas ambang tertentu, sisanya masuk tinjauan.
   - Pencarian wajah memakai foto frontal; hasil berupa tingkat kemiripan, bukan
     identitas final. Tingkat: sangat ketat 0.50, seimbang 0.60 (disarankan),
     longgar 0.68.
   - Ambang internal: auto-tag 0.45, review 0.58, margin pencocokan 0.08.
   - Data wajah disimpan sebagai encoding matematis (vektor), bukan foto mentah;
     diperlukan persetujuan anggota.
3. Face ID login anggota
   - Anggota memilih namanya, memindai wajah atau mengunggah foto frontal, dan
     menyetujui biometrik. Pendaftaran satu kali per anggota.
   - Sistem otomatis membuat akun `anggota_dewan` dan menautkannya ke dasbor.
   - Ambang login lebih ketat: tolerance 0.50 dan margin 0.03.
   - Data login disimpan di tabel terpisah `member_face_logins`; admin dapat
     menghapusnya sehingga anggota dapat mendaftar ulang.
4. Dasbor dan statistik
   - Statistik kegiatan, foto, anggota, komisi, dokumentasi terbit, tren enam bulan,
     kategori, dan penampilan terverifikasi.
   - Dasbor anggota menggabungkan dokumentasi Humas dan sentimen media.
5. Sentimen media online
   - Tavily mencari berita; Gemini menilai relevansi, identitas, dan sentimen;
     hasil dipadukan dengan leksikon sentimen Bahasa Indonesia.
   - Resolusi identitas memeriksa variasi nama/gelar, instansi, lokasi, jabatan,
     rentang tahun, dan akun resmi; berita tentang orang lain dengan nama sama
     ditolak.
   - Sentimen: positif, netral, negatif. Ini indikator awal, bukan penilaian resmi.
   - Tanpa Tavily, pemindaian dinonaktifkan. Tanpa Gemini, analisis memakai
     leksikon lokal. Hasil disimpan sebagai `media_mentions` dan `sentiment_runs`.
6. API dan integrasi
   - REST API v1 di `/api/v1`, autentikasi sesi + CSRF atau Bearer token.
   - Endpoint: `/me`, `/commissions`, `/members`, `/activities`,
     `/activities/{id}`, `/search/face`, `/stats`. Respons `{data, meta}`.
   - Token API dibuat di `/profil` atau CLI; dapat dicabut administrator.
7. Audit dan operasi
   - Audit mencatat login, Face ID, konten, wajah, sentimen, pengguna, token, komisi.
   - Ekspor CSV tersedia untuk kegiatan dan audit.
   - `/healthz` (liveness), `/readyz` (database + sinkronisasi), `/metrics`
     (opsional dilindungi `SIDEWA_METRICS_TOKEN`).

### ASISTEN SIDEWA (PANDUAN VISUAL)
- Tombol mengambang **Asisten SIDEWA** tersedia di seluruh halaman setelah pengguna
  masuk, bukan hanya halaman Humas.
- Setiap langkah menyorot satu elemen yang sedang dijelaskan: bilah atas, ikon
  pencarian/unggah/peran/profil, isi halaman (hero, statistik, filter, kartu,
  tabel, formulir, galeri, panel samping), lalu ringkasan sidebar dan seluruh
  menu navigasinya. Sorotan tidak dibatasi pada sidebar.
- Urutan panduan: sambutan → bilah atas dan ikon fitur → isi halaman yang sedang
  dibuka → sidebar → peta menu → penutup. Halaman detail dan formulir memiliki
  langkah khusus sesuai konteks.
- Panel panduan dapat diperluas, menyediakan narasi suara, dan menampilkan tautan
  untuk membuka halaman yang dijelaskan. Panduan dapat ditutup kapan saja dengan
  Esc atau tombol tutup.
- Di ponsel, sidebar bersifat off-canvas dan panel panduan tampil sebagai bottom
  sheet yang dapat diperluas. Panduan menyesuaikan tinggi viewport, orientasi,
  dan perubahan ukuran layar; target yang tersembunyi otomatis dilewati.
- Jika elemen target tidak tersedia pada halaman tersebut, langkahnya dilewati
  agar panduan tetap berjalan tanpa sorotan kosong.

### ARSITEKTUR TEKNIS
- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Jinja2, Pillow, NumPy,
  dlib + face_recognition. Frontend: HTML, CSS, JavaScript vanilla tanpa build step.
- Pengembangan: SQLite (`data/sidewa.db`). Produksi: Supabase PostgreSQL.
- Arsitektur produksi dua lapisan:
  1. Supabase PostgreSQL = sumber kebenaran (source of truth), diakses langsung
     lewat transaction pooler; memakai RLS dan mencabut akses anon/authenticated.
  2. Hugging Face S3 (`bucket=kelaska`) = penyimpanan foto/thumbnail dan Drive,
     diakses langsung lewat boto3. Media ditulis lokal sebagai cache lalu
     diunggah worker; jika cache hilang, diunduh on-demand.
- Tidak ada PostgreSQL lokal, worker outbox, maupun biner rclone.
- Sinkronisasi media dapat dipantau lewat `/readyz` (field `media_sync`).
- Pencarian wajah memakai encoding 128 dimensi dari face_recognition; jarak
  Euclidean dibandingkan dengan ambang toleransi. Detektor `hog` untuk CPU,
  `cnn` untuk GPU.
- Asisten presentasi ini memakai Gemini Live API via WebSocket. Percakapan umum
  memakai `gemini-3.8-live`; pertanyaan teknis diarahkan ke
  `gemini-3.8-live-extended-thinking` (Gemini 3.8 Live Extended Thinking) dengan
  `thinkingConfig.thinkingLevel` dari `SIDEWA_GEMINI_LIVE_THINKING_LEVEL`
  (default `low`). Audio masukan 16 kHz PCM, audio keluaran 24 kHz PCM. API key
  hanya ada di server.
- Nama model dapat disesuaikan lewat `SIDEWA_GEMINI_LIVE_MODEL`,
  `SIDEWA_GEMINI_LIVE_TECHNICAL_MODEL`, dan `SIDEWA_GEMINI_LIVE_THINKING_LEVEL`.
- Model Gemini lain: `SIDEWA_GEMINI_MODEL` (default `gemini-3.5-flash-lite`) untuk
  analisis sentimen; Tavily untuk pencarian berita.

### KEAMANAN
- Kata sandi Argon2id; minimal 10 karakter, kombinasi huruf, angka, dan simbol.
- Sesi cookie HttpOnly, SameSite=Lax, default 8 jam; Secure di produksi.
- CSRF token per sesi untuk semua POST web; Bearer token tidak memerlukan CSRF.
- RBAC berjenjang; media privat; header CSP, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, Permissions-Policy, COOP, HSTS di produksi.
- Rate limit login di Nginx; batas ukuran unggahan; validasi gambar.
- Audit log untuk aktivitas sensitif; data biometrik berupa encoding + persetujuan.
- Mode demo harus dimatikan di produksi (`SIDEWA_DEMO_MODE=false`).

### BATASAN DAN ANGKA PENTING
- 12 foto/kegiatan; 15 MB/foto; 40 MP/gambar; sesi 8 jam.
- Pencarian wajah: 0.50/0.60/0.68; auto-tag 0.45; review 0.58; login 0.50/0.03.
- Sinkronisasi: 5 detik, 200 baris/batch. Gemini timeout default 60 detik.
- Jangan mengarang jumlah anggota, kegiatan, foto, atau berita. Jika ditanya angka
  operasional terkini, gunakan ringkasan data di bawah bila tersedia; jika tidak,
  arahkan ke dasbor atau halaman statistik.

### GAYA MENJAWAB
- Mulai dari manfaat bagi anggota dewan, lalu detail teknis bila pertanyaannya teknis.
- Bahasa Indonesia sopan, tenang, jelas; hindari jargon yang tidak perlu.
- Jawaban lisan biasanya 2-4 kalimat. Untuk permintaan "jelaskan halaman ini",
  susun narasi presentasi singkat: inti halaman, manfaat, lalu ajakan/langkah berikut.
- Saat panduan visual aktif, kaitkan penjelasan dengan elemen yang sedang disorot
  (bilah atas, ikon fitur, kartu isi halaman, atau menu sidebar) agar pengguna tahu
  bagian mana yang dimaksud. Jangan menyebut elemen yang tidak disorot.
- Di ponsel, ingatkan bahwa panel panduan dapat diperluas dan sidebar dibuka lewat
  ikon menu.
- Untuk pertanyaan teknis, ikuti panduan mode teknis di bawah: jawaban boleh lebih
  panjang, terstruktur, dan rinci, tetapi tetap jelaskan dampaknya bagi pengguna.
- Jangan membahas topik di luar SIDEWA dan tugas DPRD; arahkan kembali dengan halus.
- Jangan pernah membocorkan API key, kata sandi, token, atau data pribadi mentah.
""".strip()

TECHNICAL_SUFFIX = """
### MODE TEKNIS (GEMINI 3.8 LIVE EXTENDED THINKING)
Pengguna mengajukan pertanyaan teknis. Jawab dengan kedalaman yang memadai:
- Jangan berhenti pada kalimat pembuka. Langsung berikan jawaban lengkap 4-7 kalimat.
- Awali dengan ringkasan dampak bagi pengguna atau layanan.
- Jelaskan komponen, alur data, dan kontrol keamanan yang relevan.
- Sebutkan batasan, asumsi, atau risiko bila ada.
- Bila pertanyaan menyangkut operasi produksi, tekankan prosedur dan pemantauan.
- Jangan menampilkan rahasia (API key, token, kata sandi) atau data pribadi.
""".strip()


def _system_instruction(kind: str, snapshot: str) -> str:
    base = (
        "Anda adalah \"Asisten SIDEWA\", pemandu presentasi resmi aplikasi SIDEWA "
        "milik DPRD Provinsi Riau.\n\n"
        f"{APP_KNOWLEDGE}\n\n{snapshot}"
    )
    if kind == TECHNICAL:
        return f"{base}\n\n{TECHNICAL_SUFFIX}"
    return base


def _websocket_url() -> str:
    """Bangun URL Live API dari konfigurasi Gemini tanpa membocorkan API key."""
    parts = urlsplit(settings.gemini_api_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    host = parts.netloc or "generativelanguage.googleapis.com"
    version = parts.path.strip("/").split("/")[-1] or "v1beta"
    return (
        f"{scheme}://{host}/ws/google.ai.generativelanguage.{version}."
        f"GenerativeService.BidiGenerateContent?key={quote(settings.gemini_api_key, safe='')}"
    )


def _setup_message(kind: str, snapshot: str) -> dict:
    model = settings.gemini_live_model
    generation: dict = {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {
                    "voiceName": settings.gemini_live_voice.strip() or "Aoede"
                }
            }
        },
    }
    if kind == TECHNICAL:
        model = settings.gemini_live_technical_model or model
        # Model extended thinking mewajibkan tingkat penalaran eksplisit.
        generation["thinkingConfig"] = {
            "thinkingLevel": settings.gemini_live_thinking_level.strip() or "low"
        }
    return {
        "setup": {
            "model": f"models/{model.strip() or 'gemini-3.8-live'}",
            "generationConfig": generation,
            "systemInstruction": {"parts": [{"text": _system_instruction(kind, snapshot)}]},
            "inputAudioTranscription": {"languageCodes": ["id-ID"]},
            "outputAudioTranscription": {},
        }
    }


def _context_label(index: int, title: str) -> str:
    index = max(1, min(index or 1, 10))
    title = (title or "Panduan").strip()[:90]
    return f"halaman {index} dari 10 — {title}"


def _app_snapshot(user: User, db) -> str:
    """Ringkasan data terkini agar jawaban tidak perlu mengarang angka."""
    try:
        members = db.query(func.count(Member.id)).filter(Member.is_active.is_(True)).scalar() or 0
        commissions = (
            db.query(func.count(Commission.id)).filter(Commission.is_active.is_(True)).scalar()
            or 0
        )
        activities = db.query(func.count(Activity.id)).scalar() or 0
        published = (
            db.query(func.count(Activity.id)).filter(Activity.status == "published").scalar() or 0
        )
        photos = db.query(func.count(ActivityPhoto.id)).scalar() or 0
        mentions = db.query(func.count(MediaMention.id)).scalar() or 0
        scans = db.query(func.count(SentimentRun.id)).scalar() or 0
    except Exception:  # pragma: no cover - database sibuk/tidak siap
        logger.debug("Gagal menyusun ringkasan data untuk asisten", exc_info=True)
        return ""

    role = ROLE_LABELS.get(user.role, user.role)
    scope = ""
    if user.role == ROLE_STAF and user.commission:
        scope = f" Komisi pengguna: Komisi {user.commission.code} ({user.commission.name})."
    if user.role == ROLE_ANGGOTA:
        scope = " Pengguna adalah anggota dewan; gunakan bahasa yang sederhana dan relevan."
    return (
        "### RINGKASAN DATA SAAT INI\n"
        f"- Tanggal: {date.today().isoformat()}.\n"
        f"- Pengguna yang sedang membuka panduan: {user.full_name} ({role}).{scope}\n"
        f"- Anggota aktif: {members}; komisi aktif: {commissions}.\n"
        f"- Kegiatan tercatat: {activities}; kegiatan terbit: {published}; foto: {photos}.\n"
        f"- Berita tersimpan: {mentions}; pemindaian sentimen: {scans}.\n"
        "Angka ini adalah cuplikan saat sesi dimulai; untuk data terbaru buka dasbor."
    )


@dataclass
class Upstream:
    """Satu koneksi Gemini Live (standar atau extended thinking)."""

    kind: str
    model: str
    ws: object | None = None
    reader: asyncio.Task | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    closed_event: asyncio.Event = field(default_factory=asyncio.Event)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    failed: bool = False

    @property
    def open(self) -> bool:
        return self.ws is not None and not self.closed_event.is_set()


class LiveGuide:
    """Jembatan satu pengguna antara browser dan dua sesi Gemini Live."""

    def __init__(self, websocket: WebSocket, user: User, snapshot: str) -> None:
        self.websocket = websocket
        self.user = user
        self.snapshot = snapshot
        self.sessions = {
            STANDARD: Upstream(STANDARD, settings.gemini_live_model),
            TECHNICAL: Upstream(
                TECHNICAL,
                settings.gemini_live_technical_model or settings.gemini_live_model,
            ),
        }
        self.connect_lock = asyncio.Lock()
        self.browser_lock = asyncio.Lock()
        self.audio_lock = asyncio.Lock()
        self.context = {"index": 1, "title": "Sampul"}
        self.history: list[tuple[str, str]] = []
        self.answer = ""
        self.question = ""

        self.voice_phase = "idle"  # idle | pending | standard | technical
        self.voice_target = STANDARD
        self.voice_chunks: list[str] = []
        self.voice_transcript = ""
        self.voice_ended = False
        self.voice_started = False
        self.replaying = False
        self.voice_answer_technical = False
        self.voice_technical_answered = False
        self.voice_task: asyncio.Task | None = None
        self.switch_task: asyncio.Task | None = None
        self.text_target: str | None = None
        self.pending_output: list[tuple[str, dict]] = []
        self.prewarm_task: asyncio.Task | None = None
        self.interaction_status: str | None = None
        self.saw_interaction_status = False

    # ---------------------------------------------------------------- browser
    async def send(self, payload: dict) -> bool:
        try:
            async with self.browser_lock:
                await self.websocket.send_json(payload)
            return True
        except (RuntimeError, WebSocketDisconnect):
            return False

    async def notify(self, text: str, level: str = "error") -> None:
        await self.send({"type": "notice", "level": level, "message": text})

    # --------------------------------------------------------------- upstream
    async def connect(self, kind: str) -> Upstream:
        upstream = self.sessions[kind]
        if upstream.open and upstream.ready.is_set():
            return upstream
        async with self.connect_lock:
            if upstream.open and upstream.ready.is_set():
                return upstream
            if upstream.open:
                await self._close_upstream(upstream)
            upstream.ready.clear()
            upstream.closed_event.clear()
            upstream.failed = False
            try:
                ws = await ws_connect(
                    _websocket_url(),
                    max_size=None,
                    open_timeout=max(10, min(settings.gemini_timeout, CONNECT_TIMEOUT)),
                    close_timeout=5,
                )
            except Exception as exc:
                upstream.failed = True
                logger.warning("Tidak dapat membuka sesi Live %s: %s", kind, type(exc).__name__)
                raise

            upstream.ws = ws
            await ws.send(json.dumps(_setup_message(kind, self.snapshot)))
            upstream.reader = asyncio.create_task(self._read_upstream(upstream))

            ready_task = asyncio.create_task(upstream.ready.wait())
            closed_task = asyncio.create_task(upstream.closed_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {ready_task, closed_task},
                    timeout=CONNECT_TIMEOUT,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                ready_task.cancel()
                closed_task.cancel()
            if not upstream.ready.is_set():
                upstream.failed = True
                await self._close_upstream(upstream)
                raise RuntimeError(f"Sesi Live {kind} tidak siap")

            logger.info("Sesi Live %s siap (%s)", kind, upstream.model)
            return upstream

    async def _close_upstream(self, upstream: Upstream) -> None:
        upstream.closed_event.set()
        upstream.ready.clear()
        reader = upstream.reader
        upstream.reader = None
        if reader and reader is not asyncio.current_task():
            reader.cancel()
            try:
                await reader
            except (asyncio.CancelledError, Exception):
                pass
        ws = upstream.ws
        upstream.ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def close(self) -> None:
        tasks = [self.voice_task, self.switch_task, self.prewarm_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
        for upstream in self.sessions.values():
            await self._close_upstream(upstream)

    async def _send_upstream(self, upstream: Upstream, payload: dict) -> bool:
        if not upstream.open:
            return False
        try:
            async with upstream.send_lock:
                await upstream.ws.send(json.dumps(payload))
            return True
        except Exception:
            logger.debug("Gagal mengirim ke sesi %s", upstream.kind, exc_info=True)
            return False

    async def _prewarm(self) -> None:
        """Siapkan sesi teknis di latar belakang agar perpindahan mode mulus."""
        await asyncio.sleep(0.8)
        if self.sessions[TECHNICAL].model == self.sessions[STANDARD].model:
            return
        try:
            await self.connect(TECHNICAL)
        except Exception:
            logger.info("Sesi teknis belum tersedia; akan dicoba saat dibutuhkan")

    # ---------------------------------------------------------------- readers
    async def _read_upstream(self, upstream: Upstream) -> None:
        try:
            async for raw in upstream.ws:
                try:
                    data = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                await self._handle_upstream(upstream, data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("Sesi Live %s terputus: %s", upstream.kind, type(exc).__name__)
        finally:
            upstream.closed_event.set()
            upstream.ready.clear()
            if upstream.kind == STANDARD:
                await self.send(
                    {
                        "type": "upstream_closed",
                        "message": "Koneksi asisten terputus. Klik hubungkan ulang.",
                    }
                )

    async def _handle_upstream(self, upstream: Upstream, data: dict) -> None:
        if "setupComplete" in data:
            upstream.ready.set()
            if upstream.kind == STANDARD:
                await self.send({"type": "ready"})
            return

        if "goAway" in data:
            await self.send({"type": "go_away"})
            upstream.ready.clear()
            return

        content = data.get("serverContent")
        status = data.get("interactionStatus")
        if not status and isinstance(content, dict):
            status = content.get("interactionStatus")

        if status and self._should_forward(upstream.kind):
            self.interaction_status = status
            self.saw_interaction_status = True
            if status == "IN_PROGRESS":
                await self.send({"type": "thinking"})

        if not isinstance(content, dict):
            if status == "IDLE" and self._should_forward(upstream.kind):
                await self._finish_turn(upstream.kind)
            return

        if content.get("interrupted"):
            if self._should_forward(upstream.kind):
                await self.send({"type": "interrupted"})
            return

        # Transkrip masukan hanya diteruskan dari sesi standar. Sesi teknis
        # menerima rekaman ulang audio yang sama, jadi transkripnya duplikat.
        if upstream.kind == STANDARD:
            transcription = content.get("inputTranscription") or {}
            text = transcription.get("text")
            if text:
                self.voice_transcript += str(text)
                if self.voice_started:
                    await self.send({"type": "input", "text": str(text)})
                    if (
                        not self.voice_ended
                        and self.voice_phase == "pending"
                        and not self.switch_task
                        and is_technical_question(self.voice_transcript)
                    ):
                        self.switch_task = asyncio.create_task(self._switch_to_technical())

        for part in (content.get("modelTurn") or {}).get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or {}
            audio = inline.get("data")
            if audio:
                await self._forward(
                    upstream.kind,
                    {
                        "type": "audio",
                        "data": audio,
                        "mimeType": inline.get("mimeType") or "audio/pcm;rate=24000",
                    },
                )
            text = part.get("text")
            if text:
                await self._forward(upstream.kind, {"type": "output", "text": str(text)})

        output_transcription = content.get("outputTranscription") or {}
        output_text = output_transcription.get("text")
        if output_text:
            if self._should_forward(upstream.kind) or (
                self.voice_phase == "pending" and upstream.kind == STANDARD
            ):
                self.answer += str(output_text)
            await self._forward(upstream.kind, {"type": "output", "text": str(output_text)})

        if content.get("generationComplete") and self._should_forward(upstream.kind):
            await self.send({"type": "generation_complete"})

        if content.get("turnComplete"):
            if upstream.kind == STANDARD and self.voice_phase == "pending":
                # Model sudah selesai menjawab sebelum mikrofon ditutup. Jangan
                # menahan audio terlalu lama; putuskan mode sekarang.
                if not self.switch_task and is_technical_question(self.voice_transcript):
                    self.switch_task = asyncio.create_task(self._switch_to_technical())
                elif not self.switch_task:
                    await self._release_voice(STANDARD)
            if upstream.kind == TECHNICAL and self.saw_interaction_status and status != "IDLE":
                # Extended thinking dapat mengirim beberapa ucapan dalam satu
                # interaksi. turnComplete hanya menutup ucapan, bukan sesi.
                if self._should_forward(upstream.kind):
                    await self.send({"type": "thinking"})
            elif self._should_forward(upstream.kind):
                await self._finish_turn(upstream.kind)
            return

        if status == "IDLE" and self._should_forward(upstream.kind):
            await self._finish_turn(upstream.kind)

    def _should_forward(self, kind: str) -> bool:
        if self.voice_phase == "pending":
            return False
        if self.voice_phase in {"standard", "technical"}:
            return kind == self.voice_target
        if self.text_target:
            return kind == self.text_target
        return False

    async def _forward(self, kind: str, payload: dict) -> None:
        if self.voice_phase == "pending":
            self.pending_output.append((kind, payload))
            return
        if self._should_forward(kind):
            await self.send(payload)

    async def _finish_turn(self, kind: str) -> None:
        await self.send({"type": "turn_complete"})
        if self.question:
            self.history.append((self.question, self.answer))
            self.history = self.history[-8:]
        self.question = ""
        self.answer = ""
        if self.voice_phase in {"standard", "technical"}:
            self.voice_phase = "idle"
            self.voice_target = STANDARD
            self.voice_started = False
            self.voice_ended = False
            self.voice_transcript = ""
            self.voice_chunks = []
            self.replaying = False
            self.voice_answer_technical = False
            self.voice_technical_answered = False
        self.text_target = None
        self.pending_output = []
        self.interaction_status = None
        self.saw_interaction_status = False
        await self.send({"type": "mode", "mode": STANDARD})

    # ------------------------------------------------------------------ voice
    async def _start_voice(self) -> None:
        self.voice_started = True
        self.voice_ended = False
        self.replaying = False
        self.voice_answer_technical = False
        self.voice_technical_answered = False
        self.voice_transcript = ""
        self.voice_chunks = []
        self.pending_output = []
        self.voice_phase = "pending"
        self.voice_target = STANDARD
        self.text_target = None
        self.answer = ""
        self.question = ""
        self.interaction_status = None
        self.saw_interaction_status = False
        if self.voice_task and not self.voice_task.done():
            self.voice_task.cancel()
        self.voice_task = None
        if self.switch_task and not self.switch_task.done():
            self.switch_task.cancel()
        self.switch_task = None

    async def _handle_audio(self, data: str) -> None:
        if not data:
            return
        if not self.voice_started or self.voice_phase == "idle":
            await self._start_voice()
        if not self.voice_started:
            return

        async with self.audio_lock:
            self.voice_chunks.append(data)
            if len(self.voice_chunks) > MAX_VOICE_CHUNKS:
                self.voice_chunks = self.voice_chunks[-MAX_VOICE_CHUNKS:]

            upstream = self.sessions[self.voice_target]
            if not upstream.open:
                try:
                    upstream = await self.connect(self.voice_target)
                except Exception:
                    upstream = None
                if upstream is None:
                    await self.notify(
                        "Asisten suara belum terhubung. Periksa jaringan lalu coba lagi."
                    )
                    return

            await self._send_upstream(
                upstream,
                {
                    "realtimeInput": {
                        "audio": {"data": data, "mimeType": "audio/pcm;rate=16000"}
                    }
                },
            )

    async def _handle_audio_end(self) -> None:
        if not self.voice_started:
            return
        self.voice_ended = True
        target = self.sessions[self.voice_target]
        # Gemini Live baru memproses ucapan setelah audioStreamEnd.
        if target.open:
            await self._send_upstream(
                target, {"realtimeInput": {"audioStreamEnd": True}}
            )
        if self.voice_phase == "pending" and not self.voice_task:
            self.voice_task = asyncio.create_task(self._resolve_voice())

    async def _resolve_voice(self) -> None:
        try:
            if self.voice_phase != "pending":
                return
            if self.switch_task and not self.switch_task.done():
                try:
                    await self.switch_task
                except Exception:
                    pass
                if self.voice_phase != "pending":
                    return
            await asyncio.sleep(VOICE_CLASSIFY_DELAY)
            if self.voice_phase != "pending":
                return
            if is_technical_question(self.voice_transcript):
                await self._switch_to_technical()
            else:
                await self._release_voice(STANDARD)
        finally:
            self.voice_task = None

    async def _release_voice(self, kind: str) -> None:
        self.voice_phase = "standard" if kind == STANDARD else "technical"
        self.voice_target = kind
        if not self.question:
            self.question = self.voice_transcript.strip()
        buffered = self.pending_output
        self.pending_output = []
        if kind == STANDARD:
            for source, payload in buffered:
                if source == STANDARD:
                    await self.send(payload)
        await self.send({"type": "mode", "mode": kind})

    async def _switch_to_technical(self) -> None:
        if self.voice_phase not in {"pending", "technical"}:
            return
        if self.voice_technical_answered:
            return
        if not self.voice_answer_technical:
            self.voice_answer_technical = True
            await self.send({"type": "mode", "mode": TECHNICAL})
            await self.send(
                {
                    "type": "notice",
                    "level": "info",
                    "message": "Beralih ke mode teknis (Extended Thinking).",
                }
            )
        if not self.voice_ended:
            # Ucapan masih berlangsung: biarkan audio/transkrip mengalir ke
            # sesi standar. Jawaban teknis akan diberikan setelah ucapan selesai.
            return
        await self._answer_technical_voice()

    async def _answer_technical_voice(self) -> None:
        if self.voice_technical_answered and self.voice_phase == "technical":
            return
        self.voice_technical_answered = True
        transcript = self.voice_transcript.strip()
        for _ in range(20):
            if transcript:
                break
            await asyncio.sleep(0.25)
            transcript = self.voice_transcript.strip()

        try:
            technical = await self.connect(TECHNICAL)
        except Exception:
            self.voice_answer_technical = False
            self.voice_phase = "standard"
            self.voice_target = STANDARD
            await self.notify(
                "Mode teknis belum dapat dihubungkan. Jawaban dilanjutkan dengan mode standar.",
                "warning",
            )
            if transcript:
                prompt = (
                    f"[Konteks layar presentasi: {_context_label(self.context['index'], self.context['title'])}.]\n"
                    f"Pertanyaan pengguna (dari suara): {transcript}"
                )
                self.question = transcript
                self.answer = ""
                await self._send_upstream(
                    self.sessions[STANDARD], {"realtimeInput": {"text": prompt}}
                )
            return

        self.voice_phase = "technical"
        self.voice_target = TECHNICAL
        self.pending_output = []
        self.interaction_status = None
        self.saw_interaction_status = False
        if not self.question:
            self.question = transcript
        self.answer = ""

        primer = self._history_prompt()
        parts = []
        if primer:
            parts.append(primer)
        parts.append(
            f"[Konteks layar presentasi: {_context_label(self.context['index'], self.context['title'])}.]"
        )
        parts.append(f"Pertanyaan pengguna (dari suara): {transcript}")
        prompt = "\n\n".join(parts)
        await self._send_upstream(technical, {"realtimeInput": {"text": prompt}})

    async def _cancel_generation(self) -> None:
        """Hentikan jawaban teks yang masih berjalan sebelum langkah berikutnya."""
        kind = self.text_target
        if not kind:
            return
        self.text_target = None
        self.pending_output = []
        self.question = ""
        self.answer = ""
        upstream = self.sessions.get(kind)
        if upstream and upstream.open:
            await self._close_upstream(upstream)
        await self.send({"type": "interrupted"})

    # ------------------------------------------------------------- narration
    async def _handle_narration(self, payload: dict) -> None:
        """Bacakan narasi langkah tur halaman tanpa mengubah mode percakapan."""
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        text = text[:900]
        try:
            index = int(payload.get("index") or self.context["index"])
        except (TypeError, ValueError):
            index = self.context["index"]
        title = str(payload.get("title") or self.context["title"])[:90]

        self.voice_phase = "idle"
        self.voice_started = False
        self.text_target = STANDARD
        self.question = ""
        self.answer = ""
        self.pending_output = []
        self.interaction_status = None
        self.saw_interaction_status = False
        await self.send({"type": "mode", "mode": STANDARD})

        try:
            upstream = await self.connect(STANDARD)
        except Exception:
            await self.notify(
                "Asisten suara belum dapat terhubung. Panduan tetap dapat dibaca di layar."
            )
            self.text_target = None
            return

        prompt = "\n\n".join(
            [
                f"[Konteks panduan: pengguna sedang di {_context_label(index, title)}.]",
                "[Narasi panduan: bacakan teks berikut sebagai pemandu suara. "
                "Jangan menambah pembuka, penutup, atau pertanyaan.]",
                text,
            ]
        )
        await self._send_upstream(upstream, {"realtimeInput": {"text": prompt}})

    # ------------------------------------------------------------------- text
    async def _handle_text(self, payload: dict) -> None:
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        text = text[:800]
        try:
            index = int(payload.get("index") or self.context["index"])
        except (TypeError, ValueError):
            index = self.context["index"]
        title = str(payload.get("title") or self.context["title"])[:90]
        technical = is_technical_question(text)
        kind = TECHNICAL if technical else STANDARD

        self.voice_phase = "idle"
        self.voice_started = False
        self.text_target = kind
        self.question = text
        self.answer = ""
        self.pending_output = []
        self.interaction_status = None
        self.saw_interaction_status = False
        await self.send({"type": "mode", "mode": kind})

        try:
            upstream = await self.connect(kind)
        except Exception:
            fallback = STANDARD if kind == TECHNICAL else TECHNICAL
            await self.notify(
                "Model teknis belum dapat dihubungkan. Menggunakan mode standar.",
                "warning",
            )
            try:
                upstream = await self.connect(fallback)
                kind = fallback
                self.text_target = kind
            except Exception:
                await self.notify("Asisten AI belum dapat terhubung. Periksa jaringan lalu coba lagi.")
                self.text_target = None
                return

        parts = [f"[Konteks layar presentasi: pengguna sedang membuka {_context_label(index, title)}.]"]
        history = self._history_prompt()
        if history:
            parts.append(history)
        if kind == TECHNICAL:
            parts.append(
                "[Mode teknis: jawab dengan kedalaman teknis, sebutkan komponen, alur, "
                "keamanan, dan batasan yang relevan.]"
            )
        parts.append(f"Pertanyaan pengguna: {text}")
        prompt = "\n\n".join(parts)
        await self._send_upstream(upstream, {"realtimeInput": {"text": prompt}})

    def _history_prompt(self) -> str:
        if not self.history:
            return ""
        lines = ["[Riwayat percakapan sebelumnya — hanya gunakan bila relevan]"]
        for question, answer in self.history[-4:]:
            lines.append(f"Pengguna: {question[:300]}")
            if answer:
                lines.append(f"Asisten: {answer[:400]}")
        return "\n".join(lines)

    # ------------------------------------------------------------- client loop
    async def _client_loop(self) -> None:
        while True:
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            raw = message.get("text")
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            kind = payload.get("type")
            if kind == "context":
                try:
                    self.context["index"] = int(payload.get("index") or self.context["index"])
                except (TypeError, ValueError):
                    pass
                self.context["title"] = str(payload.get("title") or self.context["title"])[:90]
            elif kind == "text":
                await self._handle_text(payload)
            elif kind == "narrate":
                await self._handle_narration(payload)
            elif kind == "cancel":
                await self._cancel_generation()
            elif kind == "audio_start":
                await self._start_voice()
            elif kind == "audio":
                await self._handle_audio(str(payload.get("data") or ""))
            elif kind == "audio_end":
                await self._handle_audio_end()

    async def run(self) -> None:
        try:
            await self.connect(STANDARD)
        except Exception:
            await self.notify(
                "Asisten Live belum dapat terhubung. Periksa koneksi atau kuota Gemini Live, "
                "lalu klik hubungkan ulang."
            )
            return
        self.prewarm_task = asyncio.create_task(self._prewarm())
        try:
            await self._client_loop()
        except WebSocketDisconnect:
            pass
        finally:
            await self.close()


@router.websocket("/panduan/live")
async def guide_live(websocket: WebSocket) -> None:
    """Jembatan audio dua arah antara browser dan Gemini Live API."""
    # Tolak koneksi lintas situs. Cookie sesi tetap SameSite=Lax, tetapi
    # pemeriksaan Origin mencegah penyalahgunaan kuota dari halaman lain.
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if origin and host and urlsplit(origin).netloc != host:
        await websocket.close(code=4403)
        return

    user_id = websocket.session.get("user_id") if websocket.session else None
    if not user_id:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            await websocket.close(code=4401)
            return
        if not settings.gemini_live_available:
            await websocket.close(code=4003)
            return
        # Muat relasi komisi sebelum sesi database ditutup.
        if user.commission is not None:
            user.commission.code  # noqa: B018
            user.commission.name  # noqa: B018
        snapshot = _app_snapshot(user, db)
    finally:
        db.close()

    await websocket.accept()
    guide = LiveGuide(websocket, user, snapshot)
    await guide.run()
