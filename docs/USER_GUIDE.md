# Panduan Pengguna SIDEWA

## Anggota Dewan
1. Buka halaman login, pilih tab **Face ID** → **Daftarkan Face ID**.
2. Pilih nama Anda pada daftar, nyalakan kamera (atau unggah foto frontal), centang
   persetujuan biometrik, lalu tekan **Daftarkan Face ID**.
3. Pendaftaran hanya dapat dilakukan satu kali per anggota dan otomatis membuat
   akun login yang terhubung dengan dashboard pribadi.
4. Setelah terdaftar, masuk cukup dengan tab **Masuk dengan wajah** dan pindai
   wajah.
5. Dashboard pribadi menampilkan dokumentasi Humas, penampilan terverifikasi,
   tren kegiatan, tugas & fungsi dewan, serta sentimen pemberitaan media online.

## Tim Humas
1. Masuk dengan akun Humas.
2. Pilih **Unggah** pada bilah atas atau menu Kegiatan.
3. Isi metadata kegiatan, pilih komisi terkait, unggah foto (maks. 12, 15 MB per foto).
4. Sistem mendeteksi wajah otomatis; tinjau hasil pada detail kegiatan.
5. Terbitkan kegiatan agar terlihat oleh staf komisi. Arsipkan bila perlu.

## Staf Komisi
1. Masuk dengan akun komisi.
2. Gunakan **Cari Wajah** untuk mengunggah foto dan menemukan anggota + kegiatan.
3. Gunakan pencarian teks untuk nama, jabatan, kategori, atau lokasi.
4. Buka detail kegiatan dan galeri dokumentasi.
5. Buka menu **Sentimen** untuk memindai dan memantau pemberitaan media online
   tentang anggota di komisi Anda. Hasil tersimpan dan tampil pada dashboard anggota.

## Administrator
- Kelola pengguna, anggota, komisi, dan log audit.
- Kelola token API untuk integrasi.
- Ekspor CSV dari halaman Kegiatan dan Audit.
- Hapus Face ID anggota dari detail anggota bila diperlukan (anggota dapat mendaftar
  ulang dari halaman login).

## Pencarian wajah
- Gunakan foto frontal yang jelas, satu wajah utama.
- Tingkat kemiripan: Sangat ketat 0.50, Seimbang 0.60 (disarankan), Longgar 0.68.
- Hasil menampilkan tingkat kemiripan, bukan identitas final; konfirmasi manual bila perlu.

## Sentimen media online
- Pemindaian menggunakan Tavily untuk mencari pemberitaan.
- Gemini menilai relevansi artikel dan sentimen terhadap anggota, lalu hasilnya
  dipadukan dengan leksikon lokal agar lebih akurat.
- Tanpa API key Tavily (`SIDEWA_TAVILY_API_KEY`), pemindaian tidak dapat dijalankan.
  Tanpa API key Gemini (`SIDEWA_GEMINI_API_KEY`), analisis otomatis memakai leksikon.
- Sentimen adalah indikator awal (positif/netral/negatif), bukan penilaian resmi
  lembaga; admin komisi tetap dapat membuka artikel sumber.
