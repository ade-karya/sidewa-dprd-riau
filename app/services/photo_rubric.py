"""Parameter baku skill **Seleksi Foto Humas**.

Modul ini adalah sumber kebenaran untuk rubrik, ambang, gerbang gagal, kode
alasan, dan target kurasi. Isinya diadaptasi dari paket skill
``seleksi-foto-humas`` (standar fotografer/editor foto profesional dan
protokoler Humas DPRD) agar dapat dipakai oleh mesin kurasi SIDEWA dengan model
Gemini 3.5 Flash Lite.

Prinsip utama:

1. **Tolak dulu, pilih kemudian.** Foto yang gagal gerbang tidak boleh menjadi
   PILIHAN berapa pun skornya.
2. **Sedikit tapi pasti bagus.** Satu momen satu foto; jangan mengisi kuota
   dengan foto lemah.
3. **Hal sensitif diputuskan manusia.** Dokumen terbaca, anak/warga rentan,
   atribut politik, atau gestur ambigu masuk PERLU_CEK.
4. **Jangan mengenali orang dari wajah.** Identitas hanya dari konteks.
"""

from __future__ import annotations

import math
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Identitas skill
# ─────────────────────────────────────────────────────────────────────────────

SKILL_KEY = "seleksi-foto-humas"
SKILL_NAME = "Seleksi Foto Humas"
SKILL_ICON = "camera"
SKILL_VERSION = "1.0"
SKILL_SIGNATURE = f"{SKILL_NAME} v{SKILL_VERSION}"

SKILL_DESCRIPTION = (
    "Kurasi foto dokumentasi kegiatan dengan standar fotografer dan protokoler "
    "DPRD: nilai teknis, komposisi, momen, dan nilai informasi; tolak yang gagal "
    "gerbang, tandai yang sensitif untuk manusia."
)

SKILL_INSTRUCTIONS = (
    f"{SKILL_SIGNATURE}. Menyeleksi foto dokumentasi kegiatan Humas DPRD dengan "
    "prinsip tolak dulu, pilih kemudian. Nilai 0-100: Teknis 30, Komposisi 25, "
    "Momen & ekspresi 25, Nilai informasi 20. PILIHAN bila skor >= 75 dan lolos "
    "semua gerbang; CADANGAN 60-74; TOLAK < 60 atau gagal gerbang. Gerbang: "
    "tokoh utama buram/wajah tidak terbaca, mata terpejam/ekspresi mengolok, "
    "tokoh terpotong/tertutup/membelakangi, peserta tidur/main HP/makan/merokok, "
    "atau gagal teknis parah. Dokumen/layar terbaca, anak/warga rentan, atribut "
    "politik, atau gestur ambigu -> PERLU_CEK, bukan diputuskan AI. Satu momen "
    "satu foto; dari foto kembar pilih satu yang terbaik. Target bawaan 10-15% "
    "dari total, minimal 8, maksimal 30 per kegiatan. Jangan mengenali orang "
    "dari wajah; gunakan keterangan pengguna, papan nama, posisi, dan konteks. "
    "Untuk paripurna cari suasana ruang, pimpinan, pembicara, ketukan palu, dan "
    "penandatanganan; untuk audiensi cari jabat tangan, cenderamata, dan foto "
    "bersama; untuk kunjungan kerja cari tokoh bersama warga/objek yang dituju. "
    "Jangan mengarang isi foto; file asli tidak diubah."
)

# ─────────────────────────────────────────────────────────────────────────────
# Bobot rubrik (total 100)
# ─────────────────────────────────────────────────────────────────────────────

TECHNICAL_MAX = 30
COMPOSITION_MAX = 25
MOMENT_MAX = 25
INFORMATION_MAX = 20
TOTAL_MAX = TECHNICAL_MAX + COMPOSITION_MAX + MOMENT_MAX + INFORMATION_MAX

DIMENSIONS = (
    ("Teknis", TECHNICAL_MAX),
    ("Komposisi", COMPOSITION_MAX),
    ("Momen & ekspresi", MOMENT_MAX),
    ("Nilai informasi", INFORMATION_MAX),
)

# ─────────────────────────────────────────────────────────────────────────────
# Ambang keputusan
# ─────────────────────────────────────────────────────────────────────────────

SELECT_SCORE = 75
BACKUP_SCORE = 60

TARGET_PERCENT_MIN = 10.0
TARGET_PERCENT_MAX = 15.0
TARGET_PERCENT_DEFAULT = 12.0
TARGET_MIN = 8
TARGET_MAX = 30

# ─────────────────────────────────────────────────────────────────────────────
# Parameter analisis lokal (indikator, bukan vonis)
# ─────────────────────────────────────────────────────────────────────────────

BLUR_THRESHOLD = 60.0
BLUR_HARD_THRESHOLD = 35.0
TILT_THRESHOLD = 2.0
LOW_CONTRAST = 28.0
HIGHLIGHT_CLIP_PERCENT = 6.0
SHADOW_CLIP_PERCENT = 25.0
COLOR_CAST = 0.30
HIGH_ISO = 6400
SLOW_SHUTTER_SECONDS = 1 / 40
MIN_LONG_EDGE = 1600
MIN_LONG_EDGE_HARD = 1000
MIN_LONG_EDGE_PRINT = 3000

DUPLICATE_HASH_DISTANCE = 12
DUPLICATE_WINDOW_SECONDS = 90
# Foto dengan kontras sangat rendah (mis. bidang warna datar) tidak dinilai
# lewat hash visual karena dHash-nya hampir identik. Hash isi (SHA-256) tetap
# dipakai untuk mendeteksi berkas yang benar-benar sama.
DUPLICATE_MIN_CONTRAST = 8.0

# ─────────────────────────────────────────────────────────────────────────────
# Gerbang gagal
# ─────────────────────────────────────────────────────────────────────────────

# (kode, penjelasan singkat, apakah keras)
GATES: tuple[tuple[str, str, bool], ...] = (
    (
        "BURAM",
        "Tokoh utama buram/tidak fokus atau wajah tokoh utama tidak terbaca",
        True,
    ),
    (
        "MATA_TERPEJAM",
        "Mata tokoh utama terpejam, atau ekspresi/gestur yang bisa dipakai mengolok-olok",
        True,
    ),
    (
        "TERPOTONG",
        "Tokoh utama terpotong parah, tertutup, atau membelakangi kamera tanpa alasan dokumentatif",
        True,
    ),
    (
        "EKSPRESI",
        "Peserta tertidur, bermain HP, makan, merokok, atau perilaku tidak pantas lain",
        True,
    ),
    (
        "SENSITIF",
        "Informasi sensitif terbaca: dokumen, layar, data pribadi, nomor telepon, pengamanan",
        False,
    ),
    (
        "PROTOKOL",
        "Atribut melanggar netralitas/protokol, atau anak/warga rentan tampil jelas tanpa konteks aman",
        False,
    ),
    (
        "GAGAL_TEKNIS",
        "Gagal teknis parah: buram parah, gelap/terang ekstrem, atau resolusi terlalu kecil",
        True,
    ),
)

HARD_GATE_CODES = {code for code, _, hard in GATES if hard}
REVIEW_GATE_CODES = {code for code, _, hard in GATES if not hard}
GATE_DESCRIPTIONS = {code: label for code, label, _ in GATES}

# ─────────────────────────────────────────────────────────────────────────────
# Kode alasan baku
# ─────────────────────────────────────────────────────────────────────────────

REASON_CODES: dict[str, str] = {
    "BURAM": "Tidak tajam / fokus meleset / goyang",
    "GELAP": "Eksposur kurang; wajah gelap",
    "TERANG": "Eksposur berlebih; wajah/putih terbakar",
    "WARNA": "Cast warna / kulit tidak natural",
    "MIRING": "Horizon/garis tegak miring",
    "RESOLUSI": "Terlalu kecil untuk tujuan pakai",
    "MATA_TERPEJAM": "Mata tokoh utama terpejam/berkedip",
    "EKSPRESI": "Ekspresi/gestur kurang pantas atau canggung",
    "TERPOTONG": "Tokoh/anggota tubuh/objek penting terpotong",
    "TERHALANG": "Wajah/objek tertutup penghalang",
    "MEMBELAKANGI": "Tokoh utama membelakangi kamera",
    "LATAR_GANGGU": "Latar belakang ramai/mengganggu",
    "KOMPOSISI": "Komposisi lemah/tidak jelas subjeknya",
    "DUPLIKAT": "Ada versi lebih baik dari momen yang sama",
    "TIDAK_INFORMATIF": "Tidak jelas kegiatan/tokoh/konteksnya",
    "PROTOKOL": "Masalah protokoler/atribut/netralitas",
    "SENSITIF": "Informasi sensitif/privasi",
    "GAGAL_TEKNIS": "Ditolak otomatis pada tahap analisis",
}

# Kode yang boleh dipakai sebagai gerbang gagal.
GATE_CODES = set(GATE_DESCRIPTIONS) | set(REASON_CODES)
# Kode yang menandakan foto harus diputuskan staf Humas, bukan AI.
REVIEW_CODES = {"SENSITIF", "PROTOKOL"}

# ─────────────────────────────────────────────────────────────────────────────
# Panduan kegiatan DPRD (dipakai di prompt dan laporan)
# ─────────────────────────────────────────────────────────────────────────────

ACTIVITY_GUIDE = (
    "Rapat paripurna/sidang: suasana ruang (wide), pimpinan di meja pimpinan, "
    "pembicara/penyampaian pendapat, ketukan palu, penandatanganan/penyerahan "
    "dokumen. Waspada anggota tertidur/main HP, kursi kosong mencolok, dokumen "
    "terbaca, layar berisi data. "
    "Rapat kerja/RDP: pimpinan rapat, mitra yang memaparkan, interaksi tanya "
    "jawab, slide paparan bila boleh dipublikasikan. Waspada rapat tertutup dan "
    "dokumen rahasia. "
    "Kunjungan kerja/sidak/reses: tokoh bersama warga/objek yang dikunjungi, "
    "suasana lokasi, dialog, peninjauan. Waspada wajah warga/anak, kondisi lokasi "
    "yang memalukan tanpa konteks, latar rumah pribadi, plat nomor. "
    "Audiensi/menerima tamu: jabat tangan, foto bersama, penyerahan cenderamata/"
    "aspirasi, suasana ruangan. Waspada pose canggung dan dokumen aspirasi berisi "
    "data pribadi. "
    "Upacara/HUT/acara resmi: pembuka, inspektur/pimpinan, pengibaran bendera, "
    "tamu undangan. Waspada atribut tidak lengkap dan bendera terbalik. "
    "Penandatanganan MoU/naskah: momen tanda tangan, tukar dokumen, foto bersama. "
    "Waspada dokumen terlalu dekat hingga isinya terbaca. "
    "Pelantikan/pengambilan sumpah: momen sumpah, penyematan, tanda tangan, "
    "keluarga. Waspada sikap sumpah tidak rapi dan kitab suci/rohaniwan salah posisi."
)

# ─────────────────────────────────────────────────────────────────────────────
# Teks rubrik untuk prompt Gemini
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_RUBRIC = f"""RUBRIK PENILAIAN (jumlahkan tepat {TOTAL_MAX}):
A. TEKNIS (0-{TECHNICAL_MAX}): fokus kritis pada mata/wajah tokoh utama (bukan
   latar/mikrofon/podium); blur gerak; eksposur wajah; highlight putih terbakar;
   shadow/gelap ekstrem; warna kulit natural; noise; distorsi lensa; flare/bercak;
   kemiringan >= {TILT_THRESHOLD:.0f} derajat; resolusi memadai.
   26-30 tajam, bersih, warna natural; 20-25 baik dengan cacat kecil; 12-19 ada
   cacat nyata; <12 cacat berat.
B. KOMPOSISI (0-{COMPOSITION_MAX}): subjek utama jelas dalam 1 detik; pembingkaian
   tidak memotong sendi; latar bersih (tiang/pohon/mikrofon tidak "tumbuh" dari
   kepala); tidak ada penghalang wajah; subjek terpisah dari latar; keseimbangan;
   kedalaman; garis/arah pandang; orientasi sesuai tujuan; gaya formal rapi.
   21-25 kuat/tepat guna; 15-20 baik; 8-14 biasa/lemah; <8 buruk.
C. MOMEN & EKSPRESI (0-{MOMENT_MAX}): momen puncak (jabat tangan menyatu,
   penyerahan, tanda tangan, palu diketuk); mata terbuka dan hidup; ekspresi
   natural/berwibawa; bahasa tubuh terbuka; interaksi nyata; arah pandang; energi.
   Momen buruk: tertidur, menguap, makan, memegang HP, menggaruk, berbisik canggung,
   melirik jam, ekspresi bosan. 21-25 kuat; 15-20 wajar; 8-14 biasa; <8 buruk.
D. NILAI INFORMASI (0-{INFORMATION_MAX}): dokumentatif (apa, siapa, di mana,
   kapan); identitas kegiatan/backdrop/logo terbaca; variasi shot (pembuka,
   medium, close-up, detail, interaksi, reaksi, foto bersama); keunikan (tidak
   mengulang); nilai berita; dampak tanpa perlu membaca keterangan.
   17-20 sangat informatif/unik; 12-16 informatif; 6-11 kurang; <6 tidak bernilai."""

PROMPT_GATES = f"""GERBANG GAGAL (override skor; foto yang kena gerbang keras TIDAK boleh
menjadi PILIHAN):
1. Tokoh utama buram/tidak fokus, atau wajah tokoh utama tidak terbaca.
2. Mata tokoh utama terpejam, atau ekspresi/gestur yang bisa dipakai mengolok-olok.
3. Tokoh utama terpotong parah, tertutup, atau membelakangi kamera tanpa alasan dokumentatif.
4. Peserta tertidur, bermain HP, makan, merokok, atau perilaku tidak pantas lain.
5. Informasi sensitif terbaca (dokumen tertutup, layar berisi data pribadi, nomor
   telepon, kata sandi, identitas aparat/pengamanan, dokumen rahasia).
6. Anak-anak/warga biasa tampak jelas dalam konteks yang bisa merugikan mereka.
7. Atribut yang melanggar netralitas/protokol (atribut partai/kampanye pada acara
   dinas, lambang/bendera salah posisi atau terbalik, atribut resmi tidak lengkap).
8. Gagal teknis parah (buram parah, gelap/terang ekstrem, resolusi terlalu kecil).

Poin 5, 6, dan 7 adalah keputusan manusia: set needs_review=true, verdict=review,
dan isi review_reason. Jangan menolak atau memilih sendiri."""

# ─────────────────────────────────────────────────────────────────────────────
# Fungsi bantu
# ─────────────────────────────────────────────────────────────────────────────


def clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    """Batasi nilai numerik; nilai tidak valid menjadi ``default``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def normalize_codes(value: Any) -> list[str]:
    """Normalisasi daftar kode alasan dari Gemini/CSV.

    Menerima list atau string yang dipisah koma/titik koma/spasi. Hanya kode
    baku yang dipertahankan agar laporan tetap seragam.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = str(value).replace(";", ",").replace("|", ",").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        for token in str(raw or "").replace("/", " ").split():
            code = token.strip().upper().strip(".,;:-")
            if not code or code not in REASON_CODES or code in seen:
                continue
            seen.add(code)
            result.append(code)
    return result


def hard_gate_codes(codes: list[str] | set[str]) -> list[str]:
    return [code for code in codes if code in HARD_GATE_CODES]


def review_gate_codes(codes: list[str] | set[str]) -> list[str]:
    return [code for code in codes if code in REVIEW_CODES]


def score_from_parts(
    technical: Any,
    composition: Any,
    moment: Any,
    information: Any,
) -> int:
    """Hitung skor total 0-100 dari empat komponen rubrik."""
    total = (
        clamp(technical, 0, TECHNICAL_MAX)
        + clamp(composition, 0, COMPOSITION_MAX)
        + clamp(moment, 0, MOMENT_MAX)
        + clamp(information, 0, INFORMATION_MAX)
    )
    return int(round(clamp(total, 0, TOTAL_MAX)))


def verdict_for(
    score: int,
    codes: list[str] | set[str],
    *,
    model_verdict: str = "",
    select_score: int = SELECT_SCORE,
    backup_score: int = BACKUP_SCORE,
) -> str:
    """Tentukan verdict akhir dengan urutan: review -> gerbang -> ambang -> model."""
    code_set = set(codes)
    if code_set & REVIEW_CODES:
        return "review"
    if code_set & HARD_GATE_CODES:
        return "rejected"
    if score < backup_score:
        return "rejected"
    if model_verdict == "rejected":
        return "rejected"
    if model_verdict == "backup":
        return "backup"
    if score >= select_score:
        return "selected"
    return "backup"


def default_target_count(
    total: int,
    requested: int = 0,
    *,
    percent: float = TARGET_PERCENT_DEFAULT,
    minimum: int = TARGET_MIN,
    maximum: int = TARGET_MAX,
) -> int:
    """Jumlah target pilihan: 10-15% dari total, min 8, maks 30.

    ``requested`` > 0 dipakai apa adanya (tetap dibatasi jumlah foto).
    """
    if total <= 0:
        return 0
    if requested and requested > 0:
        return min(total, int(requested))
    percent = clamp(percent, TARGET_PERCENT_MIN, TARGET_PERCENT_MAX, TARGET_PERCENT_DEFAULT)
    raw = math.ceil(total * percent / 100.0)
    target = max(int(minimum), min(int(maximum), raw))
    return max(0, min(total, target))


def parameter_summary() -> dict[str, Any]:
    """Ringkasan parameter untuk halaman skill dan dokumentasi."""
    return {
        "key": SKILL_KEY,
        "name": SKILL_NAME,
        "version": SKILL_VERSION,
        "description": SKILL_DESCRIPTION,
        "dimensions": [{"label": label, "max": value} for label, value in DIMENSIONS],
        "select_score": SELECT_SCORE,
        "backup_score": BACKUP_SCORE,
        "target_percent_min": TARGET_PERCENT_MIN,
        "target_percent_max": TARGET_PERCENT_MAX,
        "target_percent_default": TARGET_PERCENT_DEFAULT,
        "target_min": TARGET_MIN,
        "target_max": TARGET_MAX,
        "gates": [
            {"code": code, "label": label, "hard": hard}
            for code, label, hard in GATES
        ],
        "hard_gate_codes": sorted(HARD_GATE_CODES),
        "review_codes": sorted(REVIEW_CODES),
        "reason_codes": [
            {"code": code, "label": label} for code, label in REASON_CODES.items()
        ],
        "reason_labels": dict(REASON_CODES),
        "duplicate": {
            "hash_distance": DUPLICATE_HASH_DISTANCE,
            "window_seconds": DUPLICATE_WINDOW_SECONDS,
            "min_contrast": DUPLICATE_MIN_CONTRAST,
        },
        "technical": {
            "blur_threshold": BLUR_THRESHOLD,
            "blur_hard_threshold": BLUR_HARD_THRESHOLD,
            "tilt_threshold": TILT_THRESHOLD,
            "low_contrast": LOW_CONTRAST,
            "highlight_clip_percent": HIGHLIGHT_CLIP_PERCENT,
            "shadow_clip_percent": SHADOW_CLIP_PERCENT,
            "color_cast": COLOR_CAST,
            "high_iso": HIGH_ISO,
            "slow_shutter_seconds": SLOW_SHUTTER_SECONDS,
            "min_long_edge": MIN_LONG_EDGE,
            "min_long_edge_hard": MIN_LONG_EDGE_HARD,
            "min_long_edge_print": MIN_LONG_EDGE_PRINT,
        },
    }
