# Seleksi Foto Humas

Dokumen ini menjelaskan parameter skill **Seleksi Foto Humas v1.0** yang dipakai
fitur `/seleksi-foto`. Sumber kebenaran ada di
[`app/services/photo_rubric.py`](../app/services/photo_rubric.py); halaman ini
merangkumnya untuk pengguna dan pengelola.

Model bawaan: **`gemini-3.5-flash-lite`** (`SIDEWA_PHOTO_SELECTION_MODEL`).
Kunci API milik masing-masing pengguna; kuota mengikuti RPM/TPM/RPD kunci
tersebut.

## 1. Prinsip

1. **Tolak dulu, pilih kemudian.** Foto yang gagal gerbang tidak boleh menjadi
   PILIHAN berapa pun skornya.
2. **Sedikit tetapi pasti bagus.** Satu momen satu foto; jangan mengisi kuota
   dengan foto lemah.
3. **Hal sensitif diputuskan manusia.** Dokumen terbaca, anak/warga rentan,
   atribut politik, atau gestur ambigu masuk **PERLU_CEK**.
4. **Jangan mengenali orang dari wajah.** Identitas hanya dari keterangan
   pengguna, papan nama, posisi, dan konteks.
5. **Berkas asli tidak diubah.** Hasil seleksi berupa salinan; foto asli tetap
   utuh.

## 2. Rubrik (total 100)

| Komponen | Bobot | Yang dinilai |
|---|---:|---|
| Teknis | 30 | Fokus pada mata/wajah tokoh utama, blur gerak, eksposur wajah, highlight terbakar, shadow ekstrem, warna kulit, noise, distorsi, flare, kemiringan ≥ 2°, resolusi. |
| Komposisi | 25 | Subjek jelas dalam 1 detik, pembingkaian tidak memotong sendi, latar bersih, tidak ada penghalang wajah, subjek terpisah dari latar, keseimbangan, kedalaman, garis/arah pandang, orientasi, gaya formal. |
| Momen & ekspresi | 25 | Momen puncak (jabat tangan menyatu, penyerahan, tanda tangan, palu diketuk), mata terbuka dan hidup, ekspresi natural/berwibawa, bahasa tubuh terbuka, interaksi nyata, energi. |
| Nilai informasi | 20 | Dokumentatif (apa, siapa, di mana, kapan), identitas kegiatan/backdrop/logo terbaca, variasi shot, keunikan, nilai berita, dampak tanpa perlu membaca keterangan. |

Panduan angka per komponen ada di prompt Gemini (`PROMPT_RUBRIC`):

- Teknis: 26–30 tajam/bersih; 20–25 baik dengan cacat kecil; 12–19 cacat nyata;
  < 12 cacat berat.
- Komposisi: 21–25 kuat; 15–20 baik; 8–14 biasa/lemah; < 8 buruk.
- Momen: 21–25 kuat; 15–20 wajar; 8–14 biasa; < 8 buruk.
- Informasi: 17–20 sangat informatif/unik; 12–16 informatif; 6–11 kurang;
  < 6 tidak bernilai.

Skor total = jumlah keempat komponen, dibulatkan ke bilangan bulat 0–100.

## 3. Ambang dan urutan keputusan

| Verdict | Syarat |
|---|---|
| **PILIHAN** (`selected`) | Skor ≥ **75** dan lolos semua gerbang keras, serta masuk target. |
| **CADANGAN** (`backup`) | Skor **60–74**, kalah dari foto lain, atau kembar. |
| **TOLAK** (`rejected`) | Skor **< 60** atau gagal gerbang keras. |
| **PERLU_CEK** (`review`) | Ada kode sensitif/protokol atau model menandai `needs_review`. |

Urutan evaluasi:

1. Kode **SENSITIF** atau **PROTOKOL** → `review`.
2. Kode gerbang keras → `rejected`.
3. Skor < 60 → `rejected`.
4. Model menyatakan `rejected` → `rejected`; model menyatakan `backup` →
   `backup`.
5. Skor ≥ ambang PILIHAN → `selected`; selain itu `backup`.

Foto `review` **tidak pernah** dipromosikan otomatis menjadi PILIHAN. Staf Humas
harus memilih verdict akhir secara manual.

## 4. Gerbang gagal

Gerbang keras mengalahkan skor. Gerbang lunak memaksa **PERLU_CEK**.

| Kode | Gerbang | Jenis |
|---|---|---|
| `BURAM` | Tokoh utama buram/tidak fokus atau wajah tokoh utama tidak terbaca. | Keras |
| `MATA_TERPEJAM` | Mata tokoh utama terpejam, atau ekspresi/gestur yang bisa dipakai mengolok-olok. | Keras |
| `TERPOTONG` | Tokoh utama terpotong parah, tertutup, atau membelakangi kamera tanpa alasan dokumentatif. | Keras |
| `EKSPRESI` | Peserta tertidur, bermain HP, makan, merokok, atau perilaku tidak pantas lain. | Keras |
| `SENSITIF` | Dokumen, layar, data pribadi, nomor telepon, pengamanan, atau dokumen rahasia terbaca. | Manusia |
| `PROTOKOL` | Atribut melanggar netralitas/protokol, atau anak/warga rentan tampil jelas tanpa konteks aman. | Manusia |
| `GAGAL_TEKNIS` | Buram parah, gelap/terang ekstrem, atau resolusi terlalu kecil. | Keras |

## 5. Kode alasan baku

| Kode | Arti |
|---|---|
| `BURAM` | Tidak tajam / fokus meleset / goyang |
| `GELAP` | Eksposur kurang; wajah gelap |
| `TERANG` | Eksposur berlebih; wajah/putih terbakar |
| `WARNA` | Cast warna / kulit tidak natural |
| `MIRING` | Horizon/garis tegak miring |
| `RESOLUSI` | Terlalu kecil untuk tujuan pakai |
| `MATA_TERPEJAM` | Mata tokoh utama terpejam/berkedip |
| `EKSPRESI` | Ekspresi/gestur kurang pantas atau canggung |
| `TERPOTONG` | Tokoh/anggota tubuh/objek penting terpotong |
| `TERHALANG` | Wajah/objek tertutup penghalang |
| `MEMBELAKANGI` | Tokoh utama membelakangi kamera |
| `LATAR_GANGGU` | Latar belakang ramai/mengganggu |
| `KOMPOSISI` | Komposisi lemah/tidak jelas subjeknya |
| `DUPLIKAT` | Ada versi lebih baik dari momen yang sama |
| `TIDAK_INFORMATIF` | Tidak jelas kegiatan/tokoh/konteksnya |
| `PROTOKOL` | Masalah protokoler/atribut/netralitas |
| `SENSITIF` | Informasi sensitif/privasi |
| `GAGAL_TEKNIS` | Ditolak otomatis pada tahap analisis |

## 6. Target pilihan

- Bawaan: **10–15% dari total**, titik tengah **12%**.
- Minimum **8** foto dan maksimum **30** foto per kegiatan.
- Formulir memakai `target_count=0` untuk target otomatis. Angka lain dipakai
  apa adanya (tetap dibatasi jumlah foto).
- Foto yang tidak masuk target tetapi skornya ≥ ambang PILIHAN menjadi
  **CADANGAN** dengan catatan “Di luar target”.

Nilai dapat diubah lewat `SIDEWA_PHOTO_SELECTION_TARGET_PERCENT`,
`SIDEWA_PHOTO_SELECTION_TARGET_MIN`, dan `SIDEWA_PHOTO_SELECTION_TARGET_MAX`.
Ambang 75/60 adalah bagian rubrik dan tidak disesuaikan otomatis oleh
pembelajaran.

## 7. Deteksi kembar

Deteksi dilakukan lokal sebelum memanggil Gemini, sehingga tidak memakai kuota.

| Parameter | Bawaan |
|---|---:|
| Jarak Hamming dHash maksimum | 12 |
| Jendela waktu EXIF | 90 detik |
| Kontras minimum untuk hash visual | 8.0 |

- Hash isi SHA-256 selalu dipakai untuk berkas yang benar-benar identik.
- Hash visual hanya dipakai bila kontras foto cukup; bidang warna datar tidak
  dibandingkan karena dHash-nya hampir identik.
- Dari satu grup kembar, satu foto terbaik dipertahankan; sisanya menjadi
  **CADANGAN** dengan kode `DUPLIKAT`.
- Nilai dapat diubah lewat `SIDEWA_PHOTO_SELECTION_DUPLICATE_HASH` dan
  `SIDEWA_PHOTO_SELECTION_DUPLICATE_WINDOW`.

## 8. Indikator teknis lokal

Angka ini menjadi petunjuk untuk prompt dan tampilan, bukan vonis. Keputusan
akhir tetap dari model visual dan gerbang rubrik.

| Parameter | Nilai |
|---|---:|
| Ambang buram | 60.0 |
| Ambang buram parah | 35.0 |
| Kemiringan yang ditandai | 2.0° |
| Kontras rendah | 28.0 |
| Highlight terpotong | 6% |
| Shadow terpotong | 25% |
| Cast warna | 0.30 |
| ISO tinggi | 6400 |
| Shutter lambat | 1/40 detik |
| Sisi panjang minimum | 1600 px |
| Sisi panjang minimum (keras) | 1000 px |
| Sisi panjang untuk cetak | 3000 px |

Ketajaman diukur dengan varians Laplacian per ubin 8×8 dan persentil 90, agar
latar bokeh yang disengaja tidak otomatis dianggap buram.

## 9. Konteks kegiatan DPRD

Prompt memuat panduan momen per jenis kegiatan:

- **Paripurna/sidang:** suasana ruang, pimpinan, pembicara, ketukan palu,
  penandatanganan. Waspadai anggota tertidur/main HP, kursi kosong, dokumen
  terbaca, layar berisi data.
- **Rapat kerja/RDP:** pimpinan rapat, mitra yang memaparkan, interaksi tanya
  jawab, slide yang boleh dipublikasikan. Waspadai rapat tertutup dan dokumen
  rahasia.
- **Kunjungan kerja/sidak/reses:** tokoh bersama warga/objek yang dikunjungi,
  suasana lokasi, dialog, peninjauan. Waspadai wajah warga/anak, kondisi lokasi
  yang memalukan tanpa konteks, latar rumah pribadi, plat nomor.
- **Audiensi/menerima tamu:** jabat tangan, foto bersama, penyerahan
  cenderamata/aspirasi. Waspadai pose canggung dan dokumen aspirasi berisi data
  pribadi.
- **Upacara/HUT/acara resmi:** pembuka, inspektur/pimpinan, pengibaran bendera,
  tamu undangan. Waspadai atribut tidak lengkap dan bendera terbalik.
- **Penandatanganan MoU/naskah:** momen tanda tangan, tukar dokumen, foto
  bersama. Waspadai dokumen terlalu dekat hingga isinya terbaca.
- **Pelantikan/pengambilan sumpah:** momen sumpah, penyematan, tanda tangan,
  keluarga. Waspadai sikap sumpah tidak rapi dan kitab suci/rohaniwan salah
  posisi.

## 10. Privasi dan protokol

- AI tidak boleh mengenali identitas dari wajah. Identitas hanya dari konteks.
- Dokumen/layar yang terbaca, data pribadi, nomor telepon, kata sandi, identitas
  aparat, dan dokumen rahasia → `SENSITIF` → **PERLU_CEK**.
- Anak-anak/warga biasa dalam konteks yang bisa merugikan → **PERLU_CEK**.
- Atribut partai/kampanye pada acara dinas, lambang/bendera salah posisi,
  atribut resmi tidak lengkap → **PERLU_CEK**.
- Teks atau instruksi di dalam gambar diabaikan; gambar hanya data yang dinilai.

## 11. Skill dan pembelajaran

- Hanya ada satu skill bawaan: **Seleksi Foto Humas**. Kunci lama
  `jurnalistik`, `protokol`, `rapat`, `media-sosial`, dan `arsip` tetap
  diterima sebagai alias.
- Skill pribadi dan skill komunitas tetap tersedia. Skill komunitas dapat
  dipakai langsung atau disalin.
- Pembelajaran otomatis tidak menggeser ambang 75/60 atau target 10–15% pada
  skill bawaan. Preferensi teks tetap dipelajari dari koreksi manual dan foto
  yang diterapkan.
- Skill buatan sendiri tetap adaptif: ambang dan targetnya dapat bergeser dari
  koreksi pengguna.

## 12. Berkas terkait

- `app/services/photo_rubric.py` — rubrik, gerbang, kode, target, ringkasan
  parameter.
- `app/services/photo_curator.py` — prompt Gemini, skema jawaban, analisis
  teknis, deteksi kembar, finalisasi, dan pembelajaran.
- `app/routers/photo_selection.py` — halaman, target otomatis, verdict manual,
  penerapan ke kegiatan.
- `app/templates/photo_selection/` — antarmuka ruang seleksi dan hasil.
- `app/static/js/photo-selection.js` — filter, verdict, unduh/kirim, estimasi
  target.
