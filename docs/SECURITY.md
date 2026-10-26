# Keamanan SIDEWA

- Kata sandi di-hash dengan Argon2id; kebijakan minimal 10 karakter, kombinasi huruf, angka, dan simbol.
- Sesi cookie HttpOnly, SameSite=lax, masa berlaku dapat diatur; `Secure` otomatis di produksi.
- CSRF token per sesi; semua POST web divalidasi.
- RBAC: `superadmin`, `admin`, `humas`, `staf_komisi`, `pimpinan`, `anggota_dewan`.
- Media privat: `/media/{path}` memeriksa visibilitas kegiatan dan kepemilikan.
- Header keamanan: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP, HSTS (produksi).
- Pembatasan ukuran unggahan dan rate limit login (Nginx contoh).
- Audit log untuk login, konten, wajah, dan administrasi pengguna.
- Data biometrik disimpan sebagai encoding matematis, bukan foto mentah; persetujuan dicatat.
- Face ID login anggota disimpan pada tabel terpisah (`member_face_logins`) dengan
  akun `anggota_dewan` yang terbentuk otomatis; penghapusan dapat dilakukan administrator.
- Nonaktifkan `SIDEWA_DEMO_MODE` di produksi; akun demo tidak dibuat.
- Gunakan `SIDEWA_METRICS_TOKEN` untuk melindungi `/metrics`.
