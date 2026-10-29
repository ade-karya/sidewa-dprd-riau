# Foto Staf Humas

Folder ini dipakai `python -m app.cli seed --force` untuk mengisi foto resmi
33 staf Humas Sekretariat DPRD Provinsi Riau.

## Cara menambahkan foto

Simpan foto potret (JPG/PNG/WEBP, disarankan potret tegak dengan sisi
terpanjang minimal 1000 px) dengan salah satu pola nama berikut:

1. **Nomor urut** — `01.jpg` sampai `33.jpg`, mengikuti urutan staf pada
   `HUMAS_STAFF` di `app/services/seed.py`.
2. **Nama ternormalisasi** — huruf kecil, spasi dan tanda baca diganti `-`.
   Contoh: `radinal-munandar-s-stp-m-m-m-ip.jpg`,
   `wahyu-jati-wibowo.jpg`.

Nomor urut diperiksa lebih dulu, lalu nama ternormalisasi. Jika tidak ada
berkas yang cocok, kartu staf memakai inisial sebagai placeholder.

## Tanpa menjalankan seed ulang

Administrator dapat mengunggah foto satu per satu melalui halaman
**Staf Humas → buka ruang kerja staf → Foto profil**, atau endpoint
`POST /staf-humas/{id}/foto`.

## Catatan

- Foto akan dinormalisasi (dipangkas metadata EXIF, dikonversi ke JPEG, dan
  dibuat versi thumbnail) sebelum disimpan di `media/staff/`. Thumbnail foto
  staf disimpan hingga 1200 px agar tetap tajam pada layar beresolusi tinggi.
- Gunakan foto resmi dengan izin dari yang bersangkutan.
