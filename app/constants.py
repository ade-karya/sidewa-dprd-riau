"""Konstanta domain aplikasi."""

from __future__ import annotations

ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
ROLE_HUMAS = "humas"
ROLE_STAF = "staf_komisi"
ROLE_PIMPINAN = "pimpinan"
ROLE_ANGGOTA = "anggota_dewan"
ROLE_STAF_HUMAS = "staf_humas"

# Akun anggota dewan dan staf Humas dibuat otomatis saat pendaftaran Face ID
# di halaman login. Peran ini sengaja tidak dimasukkan ke ROLES agar tidak bisa
# dibuat manual tanpa terhubung ke data orang yang sah.
ROLES = [
    ROLE_SUPERADMIN,
    ROLE_ADMIN,
    ROLE_HUMAS,
    ROLE_STAF,
    ROLE_PIMPINAN,
]

ROLE_LABELS = {
    ROLE_SUPERADMIN: "Super Admin",
    ROLE_ADMIN: "Administrator",
    ROLE_HUMAS: "Tim Humas",
    ROLE_STAF: "Staf Komisi",
    ROLE_PIMPINAN: "Pimpinan",
    ROLE_ANGGOTA: "Anggota Dewan",
    ROLE_STAF_HUMAS: "Staf Humas",
}

ROLE_DESCRIPTIONS = {
    ROLE_SUPERADMIN: "Akses penuh termasuk konfigurasi sistem dan pengguna.",
    ROLE_ADMIN: "Mengelola konten, anggota, pengguna, dan audit.",
    ROLE_HUMAS: "Mengunggah, menyunting, dan menerbitkan dokumentasi kegiatan.",
    ROLE_STAF: "Mencari, membaca dokumentasi, dan menjalankan pemindaian sentimen komisi.",
    ROLE_PIMPINAN: "Melihat seluruh dokumentasi, statistik, dan laporan.",
    ROLE_ANGGOTA: "Dashboard pribadi anggota dewan, dokumentasi Humas, dan sentimen publik.",
    ROLE_STAF_HUMAS: "Ruang kerja pribadi staf Humas, unggahan dokumentasi, dan Face ID.",
}

CONTENT_MANAGER_ROLES = {ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_HUMAS, ROLE_STAF_HUMAS}
ADMIN_ROLES = {ROLE_SUPERADMIN, ROLE_ADMIN}
AUDIT_ROLES = {ROLE_SUPERADMIN, ROLE_ADMIN}
SENTIMENT_ROLES = {ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_STAF}
STAFF_VIEW_ROLES = {
    ROLE_SUPERADMIN,
    ROLE_ADMIN,
    ROLE_HUMAS,
    ROLE_PIMPINAN,
    ROLE_STAF_HUMAS,
}
ALL_ROLES = set(ROLES) | {ROLE_ANGGOTA, ROLE_STAF_HUMAS}

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

STATUSES = [STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVED]
STATUS_LABELS = {
    STATUS_DRAFT: "Draf",
    STATUS_PUBLISHED: "Terbit",
    STATUS_ARCHIVED: "Diarsipkan",
}

SELECTION_QUEUED = "queued"
SELECTION_RUNNING = "running"
SELECTION_PAUSED = "paused"
SELECTION_DONE = "done"
SELECTION_FAILED = "failed"
SELECTION_CANCELLED = "cancelled"

SELECTION_STATUS_LABELS = {
    SELECTION_QUEUED: "Dalam antrean",
    SELECTION_RUNNING: "Berjalan",
    SELECTION_PAUSED: "Jeda kuota",
    SELECTION_DONE: "Selesai",
    SELECTION_FAILED: "Gagal",
    SELECTION_CANCELLED: "Dibatalkan",
}

SELECTION_STATUS_TONES = {
    SELECTION_QUEUED: "gray",
    SELECTION_RUNNING: "gold",
    SELECTION_PAUSED: "blue",
    SELECTION_DONE: "green",
    SELECTION_FAILED: "red",
    SELECTION_CANCELLED: "gray",
}

SELECTION_PENDING = "pending"
SELECTION_SELECTED = "selected"
SELECTION_BACKUP = "backup"
SELECTION_REJECTED = "rejected"
SELECTION_FAILED_ITEM = "failed"

SELECTION_VERDICT_LABELS = {
    SELECTION_PENDING: "Menunggu",
    SELECTION_SELECTED: "Dipilih",
    SELECTION_BACKUP: "Cadangan",
    SELECTION_REJECTED: "Ditolak",
    SELECTION_FAILED_ITEM: "Gagal dinilai",
}

SELECTION_VERDICT_TONES = {
    SELECTION_PENDING: "gray",
    SELECTION_SELECTED: "green",
    SELECTION_BACKUP: "gold",
    SELECTION_REJECTED: "red",
    SELECTION_FAILED_ITEM: "red",
}

PHOTO_PENDING = "pending"
PHOTO_PROCESSING = "processing"
PHOTO_READY = "ready"
PHOTO_FAILED = "failed"

PHOTO_STATUS_LABELS = {
    PHOTO_PENDING: "Menunggu",
    PHOTO_PROCESSING: "Memproses",
    PHOTO_READY: "Selesai",
    PHOTO_FAILED: "Gagal",
}

CATEGORIES = [
    "Rapat Paripurna",
    "Rapat Kerja",
    "Rapat Dengar Pendapat",
    "Kunjungan Kerja",
    "Reses",
    "Sosialisasi",
    "Monitoring",
    "Pelantikan",
    "Lainnya",
]

CATEGORY_TONES = {
    "Rapat Paripurna": "purple",
    "Rapat Kerja": "blue",
    "Rapat Dengar Pendapat": "cyan",
    "Kunjungan Kerja": "gold",
    "Reses": "pink",
    "Sosialisasi": "green",
    "Monitoring": "blue",
    "Pelantikan": "purple",
    "Lainnya": "gray",
}

COMMISSION_COLORS = ["#7E4890", "#3C8DAD", "#C08A2E", "#5B8C5A", "#B85C7A"]

FACE_SOURCE_AUTO = "auto"
FACE_SOURCE_CONFIRMED = "confirmed"
FACE_SOURCE_MANUAL = "manual"

AUDIT_ACTIONS = {
    "LOGIN": "Masuk",
    "LOGIN_FAILED": "Gagal masuk",
    "LOGOUT": "Keluar",
    "FACE_LOGIN": "Masuk dengan Face ID",
    "FACE_LOGIN_FAILED": "Gagal Face ID",
    "FACE_LOGIN_ENROLL": "Daftarkan Face ID",
    "FACE_LOGIN_DELETE": "Hapus Face ID",
    "STAFF_PORTRAIT_UPDATE": "Ubah foto staf",
    "SENTIMENT_SEARCH": "Pindai sentimen",
    "SENTIMENT_SEARCH_FAILED": "Pindai sentimen gagal",
    "ACTIVITY_CREATE": "Buat kegiatan",
    "ACTIVITY_UPDATE": "Ubah kegiatan",
    "ACTIVITY_PUBLISH": "Terbitkan kegiatan",
    "ACTIVITY_ARCHIVE": "Arsipkan kegiatan",
    "ACTIVITY_DELETE": "Hapus kegiatan",
    "RELEASE_CREATE": "Buat rilis",
    "RELEASE_UPDATE": "Ubah rilis",
    "RELEASE_PUBLISH": "Terbitkan rilis",
    "RELEASE_ARCHIVE": "Arsipkan rilis",
    "RELEASE_DELETE": "Hapus rilis",
    "PHOTO_UPLOAD": "Unggah foto",
    "PHOTO_DELETE": "Hapus foto",
    "PHOTO_PROCESS": "Proses wajah",
    "PHOTO_PROCESS_FAILED": "Gagal proses wajah",
    "FACE_ENROLL": "Daftarkan wajah",
    "FACE_DELETE": "Hapus data wajah",
    "FACE_CONFIRM": "Konfirmasi wajah",
    "FACE_REJECT": "Tolak deteksi wajah",
    "MEMBER_CREATE": "Tambah anggota",
    "MEMBER_UPDATE": "Ubah anggota",
    "MEMBER_DEACTIVATE": "Nonaktifkan anggota",
    "MEMBER_ADD": "Tag anggota kegiatan",
    "MEMBER_REMOVE": "Lepas tag anggota",
    "SEARCH_FACE": "Pencarian wajah",
    "USER_CREATE": "Tambah pengguna",
    "USER_UPDATE": "Ubah pengguna",
    "USER_DEACTIVATE": "Nonaktifkan pengguna",
    "USER_PASSWORD": "Reset kata sandi",
    "TOKEN_CREATE": "Buat token API",
    "TOKEN_REVOKE": "Cabut token API",
    "COMMISSION_UPDATE": "Ubah komisi",
    "AI_KEY_SAVE": "Simpan kunci AI",
    "AI_KEY_TEST": "Uji kunci AI",
    "AI_KEY_DELETE": "Hapus kunci AI",
    "AI_SKILL_SAVE": "Simpan skill AI",
    "AI_SKILL_DELETE": "Hapus skill AI",
    "PHOTO_SELECTION_START": "Mulai seleksi foto AI",
    "PHOTO_SELECTION_VERDICT": "Ubah pilihan foto AI",
    "PHOTO_SELECTION_APPLY": "Terapkan foto pilihan",
    "PHOTO_SELECTION_EXPORT": "Unduh foto pilihan",
    "PHOTO_SELECTION_DELETE": "Hapus sesi seleksi foto",
    "PHOTO_SELECTION_CANCEL": "Batalkan seleksi foto",
    "PHOTO_SELECTION_RESUME": "Lanjutkan seleksi foto",
}
