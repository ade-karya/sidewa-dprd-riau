# Panduan Pengguna SIDEWA

## Panduan visual
- Halaman login menyediakan tombol **Kenali SIDEWA** untuk presentasi lengkap
  tentang tujuan, masalah, fitur, dan manfaat aplikasi.
- Di ruang kerja Humas, direktori **Staf Humas**, dan **Seleksi Foto**, tombol
  **Asisten SIDEWA** membuka tur halaman. Asisten menjelaskan setiap menu,
  menyorot elemen yang sedang dibahas, dan dapat membacakan narasi suara.

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
1. Masuk dengan akun Humas atau Face ID staf Humas.
2. Pilih **Unggah** pada bilah atas atau menu Kegiatan.
3. Isi metadata kegiatan, pilih komisi terkait, unggah foto (maks. 12, 15 MB per foto).
4. Sistem mendeteksi wajah otomatis; tinjau hasil pada detail kegiatan.
5. Terbitkan kegiatan agar terlihat oleh staf komisi. Arsipkan bila perlu.
6. Buka menu **Rilis** untuk menyusun siaran pers. Tautkan rilis ke kegiatan,
   simpan sebagai draf, lalu terbitkan agar dapat dibaca seluruh pengguna.

## Rilis & siaran pers
1. Buka `/rilis` atau pintasan **Tulis rilis** pada ruang kerja staf Humas.
2. Isi judul, tanggal rilis, ringkasan, isi naskah, tag, dan kegiatan terkait.
3. Simpan sebagai draf untuk ditinjau kembali. Draf hanya terlihat oleh pengelola konten.
4. Terbitkan rilis dari halaman detail. Rilis terbit tampil di daftar dan ruang kerja.
5. Gunakan **Arsipkan** untuk menyimpan rilis sebagai referensi tanpa menampilkannya
   sebagai rilis aktif. Administrator dapat menghapus rilis secara permanen.

## Drive Humas
Setiap staf Humas memiliki **Drive pribadi** berkuota **100 GB** di menu
**Drive** (`/drive`). Berkas disimpan di HF S3, terpisah dari dokumentasi
kegiatan.

1. Buka **Drive** di sidebar atau pintasan **Drive Humas** pada ruang kerja staf.
2. Halaman menampilkan bilah kuota: ruang terpakai, sisa, dan persentase. Bila
   sudah mencapai 90%, bilah berubah warna sebagai peringatan.
3. Klik **Pilih berkas** pada kartu *Unggah berkas* — beberapa berkas sekaligus
   diperbolehkan, maksimal **100 MB** per berkas dan tidak melebihi sisa kuota.
   Berkas yang terlalu besar ditolak dengan pesan sisa ruang.
4. Gunakan **Folder baru** untuk membuat subfolder. Klik nama folder untuk masuk;
   remah folder di atas untuk kembali.
5. Kolom pencarian mencari nama berkas di seluruh Drive Anda.
6. Tombol **Unduh** menyimpan berkas ke komputer. Ikon pensil mengubah nama,
   ikon tempat sampah menghapus berkas atau folder beserta isinya.
7. Bila nama berkas sama, sistem menambahkan akhiran ` (2)`, ` (3)`, dan
   seterusnya agar tidak ada berkas yang tertimpa.

**Drive tim.** Tab **Drive tim** (`/drive/tim`) menyimpan berkas bersama, misalnya
template rilis atau aset desain. Semua pengelola konten dapat membuka dan
mengubah isinya. Berkas pribadi staf tidak pernah muncul di sini.

**Untuk administrator.** Superadmin dan admin dapat memilih nama staf pada menu
**Lihat Drive staf** untuk memeriksa pemakaian ruang dan isi Drive staf tersebut.
Staf hanya melihat Drive miliknya sendiri; staf komisi dan anggota dewan tidak
memiliki akses ke Drive.

## Staf Humas Sekretariat
Setiap staf Humas memiliki **ruang kerja pribadi** di `/dashboard-staf/{id}`.
1. Buka halaman login, pilih tab **Face ID** → **Daftarkan Face ID**.
2. Pilih nama Anda pada kelompok **Staf Humas Sekretariat**, ambil foto frontal
   (atau unggah foto), centang persetujuan biometrik, lalu daftarkan.
3. Setelah terdaftar, masuk cukup dengan **Masuk dengan wajah**. Sistem otomatis
   mengarahkan ke ruang kerja pribadi.
4. Ruang kerja menampilkan unggahan dokumentasi pribadi, draf kegiatan dan draf
   rilis yang perlu diselesaikan, tren unggahan enam bulan, aktivitas terbaru tim
   Humas, status Face ID, serta pintasan tugas harian termasuk **Tulis rilis**.
5. Administrator dapat membuka direktori **Staf Humas** (`/staf-humas`) untuk
   melihat seluruh staf, mengunggah foto resmi, atau menghapus Face ID.

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
- Sebelum menilai sentimen, Gemini melakukan resolusi identitas (nama/variasi/gelar,
  instansi, lokasi, jabatan, rentang tahun, akun resmi) dan menolak berita yang
  membahas orang lain dengan nama sama (mis. anggota DPRD daerah lain).
- Untuk identitas khusus (alias, akun resmi, rentang tahun), gunakan berkas JSON
  `data/member_identity.json` (contoh: `docs/member_identity.example.json`).
