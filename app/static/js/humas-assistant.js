(() => {
  "use strict";

  const root = document.querySelector("[data-tour-root]");
  if (!root) return;

  const fab = document.querySelector("[data-tour-open]");
  const blocker = root.querySelector("[data-tour-blocker]");
  const spotlight = root.querySelector("[data-tour-spotlight]");
  const card = root.querySelector("[data-tour-card]");
  const kickerEl = root.querySelector("[data-tour-kicker]");
  const counterEl = root.querySelector("[data-tour-counter]");
  const titleEl = root.querySelector("[data-tour-title]");
  const bodyEl = root.querySelector("[data-tour-body]");
  const tipsEl = root.querySelector("[data-tour-tips]");
  const linkEl = root.querySelector("[data-tour-link]");
  const linkLabelEl = root.querySelector("[data-tour-link-label]");
  const progressEl = root.querySelector("[data-tour-progress]");
  const dotsEl = root.querySelector("[data-tour-dots]");
  const prevBtn = root.querySelector("[data-tour-prev]");
  const nextBtn = root.querySelector("[data-tour-next]");
  const nextLabel = root.querySelector("[data-tour-next-label]");
  const liveEl = root.querySelector("[data-tour-live]");
  const voiceBtn = root.querySelector("[data-tour-voice]");
  const expandBtn = root.querySelector("[data-tour-expand]");
  const statusEl = root.querySelector("[data-tour-status]");
  const headTitleEl = root.querySelector(".tour-id strong");
  const sidebarEl = document.getElementById("sidebar");

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const supportsSpeech =
    "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const supportsAudio = Boolean(window.AudioContext || window.webkitAudioContext);
  const supportsVoice = supportsAudio || supportsSpeech;
  const isSmall = () => window.matchMedia("(max-width: 760px)").matches;
  const isOffcanvasSidebar = () => window.matchMedia("(max-width: 900px)").matches;

  const PAGE_INFO = {
    "/": {
      title: "Beranda",
      body:
        "Pusat ringkasan SIDEWA. Di sini terlihat statistik dokumentasi, kegiatan terbaru, tren bulanan, dan aktivitas terakhir.",
      tips: [
        "Mulai dari kartu statistik untuk membaca kondisi arsip.",
        "Klik dokumentasi terbaru untuk membuka detail kegiatan.",
        "Gunakan pencarian di bilah atas untuk menemukan data dengan cepat.",
      ],
    },
    "/dashboard-staf": {
      title: "Ruang Kerja Humas",
      body:
        "Ruang kerja pribadi staf Humas: unggahan, draf yang perlu diselesaikan, statistik publikasi, dan status Face ID.",
      tips: [
        "Gunakan pintasan ruang kerja untuk berpindah tugas.",
        "Selesaikan draf agar dokumentasi segera tampil ke pengguna.",
        "Daftarkan Face ID dari halaman login agar bisa masuk tanpa kata sandi.",
      ],
    },
    "/dashboard-anggota": {
      title: "Dashboard Anggota",
      body:
        "Ruang pribadi anggota dewan: dokumentasi Humas, penampilan terverifikasi, tren kegiatan, sentimen media, dan tugas dewan.",
      tips: [
        "Mulai dari kartu identitas untuk memeriksa status Face ID.",
        "Gulir ke bagian sentimen untuk membaca pemberitaan terkait.",
        "Gunakan tombol Cetak bila ringkasan perlu dibagikan.",
      ],
    },
    "/drive": {
      title: "Drive Humas",
      body:
        "Penyimpanan berkas pribadi dan tim Humas di cloud. Unggah, cari, ubah nama, unduh, dan kelola folder tanpa membebani server aplikasi.",
      tips: [
        "Periksa bilah kuota sebelum mengunggah berkas besar.",
        "Gunakan tab Drive tim untuk berkas bersama.",
        "Klik nama folder untuk masuk dan remah folder untuk kembali.",
      ],
    },
    "/staf-humas": {
      title: "Staf Humas",
      body:
        "Direktori staf Humas Sekretariat, lengkap dengan jabatan, unggahan, dan status Face ID masing-masing.",
      tips: [
        "Cari berdasarkan nama, jabatan, atau unit kerja.",
        "Klik kartu staf untuk membuka ruang kerjanya.",
        "Perhatikan penanda Face ID untuk mengetahui siapa yang sudah terdaftar.",
      ],
    },
    "/seleksi-foto": {
      title: "Seleksi Foto",
      body:
        "Ruang kurasi foto berbantuan AI. Sistem menilai kualitas, memilih foto terbaik, lalu menyiapkannya untuk diterapkan ke kegiatan.",
      tips: [
        "Pilih skill seleksi sesuai kebutuhan dokumentasi.",
        "Unggah foto, atur target dan ambang skor, lalu jalankan seleksi.",
        "Tinjau hasil sebelum menerapkannya ke kegiatan.",
      ],
    },
    "/kegiatan": {
      title: "Kegiatan",
      body:
        "Pusat dokumentasi kegiatan dewan. Di sini dokumentasi dibuat, disunting, diterbitkan, dan dilengkapi foto.",
      tips: [
        "Gunakan filter status, kategori, komisi, lokasi, dan tanggal.",
        "Buka detail kegiatan untuk mengelola foto dan anggota tertaut.",
        "Manfaatkan aksi terbitkan, arsipkan, dan ekspor CSV sesuai kebutuhan.",
      ],
    },
    "/rilis": {
      title: "Rilis",
      body:
        "Daftar siaran pers Humas. Rilis dapat ditautkan ke kegiatan agar publikasi resmi sejalan dengan dokumentasi.",
      tips: [
        "Cari rilis berdasarkan judul, status, atau rentang tanggal.",
        "Buka detail untuk membaca isi dan mengunduh rilis.",
        "Tautkan rilis ke kegiatan terkait agar konteksnya lengkap.",
      ],
    },
    "/cari": {
      title: "Cari Wajah",
      body:
        "Pencarian dokumentasi lewat wajah, nama, jabatan, komisi, lokasi, atau tanggal. Hasil wajah dilengkapi skor kecocokan.",
      tips: [
        "Unggah foto wajah yang jelas dan frontal untuk pencarian wajah.",
        "Gunakan kata kunci atau filter bila ingin hasil yang lebih sempit.",
        "Selalu verifikasi hasil pencarian sebelum dipakai sebagai bukti.",
      ],
    },
    "/anggota": {
      title: "Anggota",
      body:
        "Direktori anggota dewan: profil, jabatan, komisi, daerah pemilihan, kontak, dan data Face ID.",
      tips: [
        "Cari anggota berdasarkan nama, komisi, atau dapil.",
        "Buka profil untuk melihat rekam penampilan dan sentimen pemberitaan.",
        "Administrator dapat mengelola Face ID dari halaman detail anggota.",
      ],
    },
    "/komisi": {
      title: "Komisi",
      body:
        "Daftar komisi beserta anggota dan dokumentasi terkait. Membantu penelusuran sesuai bidang kerja dewan.",
      tips: [
        "Pilih komisi untuk melihat anggotanya.",
        "Buka dokumentasi komisi untuk menelusuri kegiatan terkait.",
        "Administrator dapat menyunting nama, bidang, dan urutan komisi.",
      ],
    },
    "/sentimen": {
      title: "Sentimen",
      body:
        "Pemantauan pemberitaan media online. Sistem menilai relevansi dan sentimen berita terhadap anggota atau komisi.",
      tips: [
        "Jalankan pemindaian untuk memperbarui berita terbaru.",
        "Baca ringkasan positif, netral, dan negatif per anggota.",
        "Gunakan hasilnya sebagai indikator awal, bukan penilaian resmi.",
      ],
    },
    "/pengguna": {
      title: "Pengguna",
      body:
        "Halaman administrator untuk mengelola akun, peran, komisi, status aktif, dan reset kata sandi.",
      tips: [
        "Periksa peran sebelum memberikan akses.",
        "Nonaktifkan akun yang tidak lagi bertugas.",
        "Reset kata sandi bila pengguna kehilangan akses.",
      ],
    },
    "/audit": {
      title: "Audit",
      body:
        "Jejak aktivitas sensitif aplikasi: login, perubahan konten, pengelolaan wajah, sentimen, pengguna, dan token.",
      tips: [
        "Gunakan filter untuk menelusuri aktivitas tertentu.",
        "Periksa kronologi sebelum mengambil tindakan.",
        "Ekspor CSV bila laporan perlu diserahkan ke pimpinan.",
      ],
    },
    "/profil": {
      title: "Profil",
      body:
        "Pengaturan akun pribadi: identitas, foto, kata sandi, dan token API untuk integrasi.",
      tips: [
        "Perbarui data profil agar komunikasi tetap akurat.",
        "Ganti kata sandi secara berkala.",
        "Cabut token API yang tidak lagi digunakan.",
      ],
    },
  };

  const PAGE_STEPS = {
    dashboard: [
      {
        selector: '[data-tour="dash-hero"]',
        kicker: "Halaman ini · Ringkasan",
        title: "Pusat ringkasan SIDEWA",
        body:
          "Hero ini menjelaskan peran aplikasi dan menyediakan aksi tercepat: cari dokumentasi, unggah kegiatan, atau jelajahi arsip.",
        tips: [
          "Gunakan Cari dokumentasi untuk membuka pencarian wajah dan teks.",
          "Tombol Unggah kegiatan hanya tampil bagi pengelola konten.",
          "Panel kanan menampilkan status mesin pengenalan wajah.",
        ],
      },
      {
        selector: '[data-tour="dash-stats"]',
        kicker: "Halaman ini · Angka kunci",
        title: "Empat kartu statistik",
        body:
          "Setiap kartu memakai ikon fitur: kalender untuk dokumentasi, centang untuk foto terbit, pengguna untuk penampilan anggota, dan basis data untuk penyimpanan.",
        tips: [
          "Bandingkan jumlah dokumentasi dengan foto untuk menilai kelengkapan arsip.",
          "Kartu penyimpanan membantu memantau kapasitas media.",
        ],
      },
      {
        selector: '[data-tour="dash-commissions"]',
        kicker: "Halaman ini · Ikon komisi",
        title: "Jelajahi dokumentasi per komisi",
        body:
          "Deretan kartu komisi memakai warna dan ikon masing-masing. Klik satu kartu untuk membuka komisi beserta dokumentasinya.",
        tips: [
          "Gunakan kartu komisi untuk mempersempit pencarian sesuai bidang.",
          "Warna kartu konsisten di seluruh halaman komisi.",
        ],
      },
      {
        selector: '[data-tour="dash-trend"]',
        kicker: "Halaman ini · Tren",
        title: "Tren dokumentasi enam bulan",
        body:
          "Grafik batang memperlihatkan ritme publikasi. Kategori terbanyak muncul di bawah grafik sebagai bahan evaluasi.",
        tips: [
          "Gunakan tren untuk merencanakan unggahan bulan berikutnya.",
          "Klik Lihat semua untuk membuka daftar kegiatan.",
        ],
      },
      {
        selector: '[data-tour="dash-top-members"]',
        kicker: "Halaman ini · Partisipasi",
        title: "Anggota paling terdokumentasi",
        body:
          "Peringkat ini dihitung dari jumlah kegiatan yang menampilkan anggota. Klik nama untuk membuka profil atau dashboard anggota.",
        tips: [
          "Gunakan daftar ini untuk melihat keterlibatan anggota.",
          "Buka dashboard anggota untuk sentimen pemberitaan terkait.",
        ],
      },
      {
        selector: '[data-tour="dash-recent"]',
        kicker: "Halaman ini · Dokumentasi",
        title: "Dokumentasi terbaru",
        body:
          "Kartu kegiatan menampilkan foto sampul, judul, tanggal, komisi, dan jumlah foto. Klik kartu untuk membuka detail.",
        tips: [
          "Perhatikan komisi dan tanggal sebelum membuka detail.",
          "Gunakan kartu untuk menelusuri dokumentasi terbaru.",
        ],
      },
      {
        selector: '[data-tour="dash-categories"]',
        kicker: "Halaman ini · Kategori",
        title: "Distribusi kategori kegiatan",
        body:
          "Panel ini merangkum kategori yang paling sering didokumentasikan beserta persentasenya.",
        tips: [
          "Gunakan filter kategori di halaman kegiatan untuk menindaklanjuti.",
          "Kategori dominan membantu menyusun rencana liputan.",
        ],
      },
      {
        selector: '[data-tour="dash-audit"]',
        kicker: "Halaman ini · Aktivitas",
        title: "Jejak aktivitas sistem",
        body:
          "Umpan audit menampilkan peristiwa terakhir yang tercatat, lengkap dengan aktor dan waktu.",
        tips: [
          "Buka log audit untuk menelusuri kronologi lengkap.",
          "Perhatikan aktivitas sensitif seperti perubahan pengguna.",
        ],
      },
    ],
    staff_dashboard: [
      {
        selector: '[data-tour="humas-hero"]',
        kicker: "Halaman ini · Profil staf",
        title: "Identitas dan ringkasan Anda",
        body:
          "Kartu ini memperlihatkan profil staf, unit kerja, status Face ID, dan angka utama unggahan Anda.",
        tips: [
          "Periksa status Face ID untuk memastikan login wajah aktif.",
          "Gunakan tombol Cetak bila ringkasan perlu dibagikan.",
        ],
      },
      {
        selector: '[data-tour="humas-flow"]',
        kicker: "Halaman ini · Alur kerja",
        title: "Alur kerja harian",
        body:
          "Pita alur menghubungkan seleksi foto, penulisan rilis, dan pengelolaan kegiatan dalam tiga langkah cepat.",
        tips: [
          "Ikuti alur dari kiri ke kanan sesuai tugas hari ini.",
          "Klik salah satu langkah untuk langsung membuka halamannya.",
        ],
      },
      {
        selector: '[data-tour="humas-shortcuts"]',
        kicker: "Halaman ini · Pintasan",
        title: "Pintasan ruang kerja",
        body:
          "Setiap ubin memakai ikon fitur dan membuka tugas yang paling sering dipakai tim Humas, dari unggah dokumentasi sampai seleksi foto.",
        tips: [
          "Mulai dari pintasan yang sesuai tugas hari ini.",
          "Arahkan kursor untuk membaca ringkasan tiap pintasan.",
        ],
      },
      {
        selector: '[data-tour="humas-summary"]',
        kicker: "Halaman ini · Angka kunci",
        title: "Ringkasan pekerjaan",
        body:
          "Lihat jumlah draf, unggahan 30 hari, total dilihat, dan kegiatan tim dalam satu baris.",
        tips: [
          "Draf yang menunggu terbit sebaiknya diselesaikan lebih dulu.",
          "Angka dilihat membantu menilai jangkauan dokumentasi.",
        ],
      },
      {
        selector: '[data-tour="humas-drafts"]',
        kicker: "Halaman ini · Draf",
        title: "Draf yang perlu diselesaikan",
        body:
          "Daftar ini hanya muncul bila ada draf aktif. Klik salah satu untuk melanjutkan penyuntingan.",
        tips: [
          "Lengkapi metadata dan foto sebelum menerbitkan.",
          "Periksa kembali kegiatan sebelum diarsipkan.",
        ],
      },
      {
        selector: '[data-tour="humas-release"]',
        kicker: "Halaman ini · Rilis",
        title: "Rilis dan siaran pers",
        body:
          "Panel ini merangkum siaran pers yang Anda susun, termasuk draf yang perlu diselesaikan dan rilis terbaru.",
        tips: [
          "Gunakan tombol Tulis rilis untuk membuat siaran pers baru.",
          "Tautkan rilis ke kegiatan agar publikasi dan dokumentasi sejalan.",
          "Buka Semua rilis saya untuk menelusuri riwayat publikasi.",
        ],
      },
      {
        selector: '[data-tour="humas-publication"]',
        kicker: "Halaman ini · Publikasi",
        title: "Statistik publikasi",
        body:
          "Ringkasan jumlah kegiatan, publikasi terbit, draf, dan foto yang Anda unggah.",
        tips: [
          "Bandingkan jumlah draf dan terbit sebagai indikator ketuntasan.",
          "Gunakan tautan Semua dokumentasi untuk melihat keseluruhan.",
        ],
      },
      {
        selector: '[data-tour="humas-activity"]',
        kicker: "Halaman ini · Unggahan",
        title: "Dokumentasi pribadi",
        body:
          "Daftar ini memperlihatkan kegiatan yang Anda unggah atau kelola, lengkap dengan status dan jumlah foto.",
        tips: [
          "Klik kegiatan untuk memeriksa metadata dan galeri.",
          "Gunakan Lihat semua untuk membuka arsip lengkap.",
        ],
      },
      {
        selector: '[data-tour="humas-trend"]',
        kicker: "Halaman ini · Tren",
        title: "Tren unggahan enam bulan",
        body:
          "Grafik batang memperlihatkan ritme publikasi tim. Kategori terbanyak ditampilkan di bawah grafik.",
        tips: [
          "Gunakan tren untuk merencanakan dokumentasi bulan berikutnya.",
          "Klik Kelola kegiatan untuk menindaklanjuti data.",
        ],
      },
      {
        selector: '[data-tour="humas-team"]',
        kicker: "Halaman ini · Tim",
        title: "Aktivitas terbaru tim Humas",
        body:
          "Kartu kegiatan tim membantu Anda melihat publikasi terbaru dan menjaga konsistensi dokumentasi.",
        tips: [
          "Buka kartu untuk melihat detail kegiatan tim.",
          "Gunakan halaman ini sebagai referensi gaya dokumentasi.",
        ],
      },
      {
        selector: '[data-tour="humas-faceid"]',
        kicker: "Halaman ini · Keamanan",
        title: "Face ID login",
        body:
          "Panel ini menunjukkan apakah wajah Anda sudah terdaftar. Data wajah disimpan sebagai encoding biometrik, bukan foto mentah.",
        tips: [
          "Jika belum aktif, daftarkan dari halaman login.",
          "Administrator dapat menghapus Face ID bila diperlukan.",
        ],
      },
      {
        selector: '[data-tour="humas-photo"]',
        kicker: "Halaman ini · Foto profil",
        title: "Foto profil staf",
        body:
          "Foto resmi tampil di direktori dan kartu staf. Administrator dapat menggantinya dari panel ini.",
        tips: [
          "Gunakan foto frontal dengan pencahayaan yang baik.",
          "Foto baru langsung tampil di seluruh direktori.",
        ],
      },
      {
        selector: '[data-tour="humas-duties"]',
        kicker: "Halaman ini · Tugas",
        title: "Tugas dan fungsi Humas",
        body:
          "Pengingat peran tim Humas dalam dokumentasi, publikasi, dan pelayanan informasi dewan.",
        tips: [
          "Gunakan daftar ini sebagai acuan pembagian kerja.",
          "Sesuaikan prioritas dengan arahan pimpinan.",
        ],
      },
      {
        selector: '[data-tour="humas-team-summary"]',
        kicker: "Halaman ini · Ringkasan tim",
        title: "Ringkasan tim Humas",
        body:
          "Panel ini merangkum jumlah staf aktif, cakupan Face ID, kegiatan tim, dan publikasi terbit.",
        tips: [
          "Gunakan angka ini untuk menilai kapasitas tim.",
          "Buka direktori staf untuk melihat detail tiap anggota tim.",
        ],
      },
    ],
    humas_staff: [
      {
        selector: '[data-tour="humas-filter"]',
        kicker: "Halaman ini · Pencarian",
        title: "Cari staf Humas",
        body:
          "Gunakan kata kunci nama, jabatan, atau unit kerja. Filter status membantu menampilkan staf aktif atau nonaktif.",
        tips: [
          "Kosongkan kata kunci lalu klik Cari untuk melihat semua staf.",
          "Gunakan tombol Reset untuk mengembalikan filter.",
        ],
      },
      {
        selector: '[data-tour="humas-filter-meta"]',
        kicker: "Halaman ini · Hasil",
        title: "Ringkasan hasil",
        body:
          "Menampilkan jumlah staf yang cocok dan pengingat bahwa setiap staf punya ruang kerja serta Face ID.",
        tips: [
          "Periksa jumlah hasil sebelum membuka kartu staf.",
          "Gunakan pencarian ulang bila hasil terlalu banyak.",
        ],
      },
      {
        selector: '[data-tour="humas-directory"]',
        kicker: "Halaman ini · Direktori",
        title: "Kartu staf",
        body:
          "Setiap kartu memperlihatkan foto, jabatan, unit, jumlah unggahan, dan status Face ID.",
        tips: [
          "Klik kartu untuk membuka ruang kerja staf.",
          "Kartu dengan kunci berarti ruang kerja bersifat pribadi.",
        ],
      },
    ],
    photo_selection: [
      {
        selector: '[data-tour="ps-hero"]',
        kicker: "Halaman ini · Ringkasan",
        title: "Ringkasan seleksi foto",
        body:
          "Menampilkan status kunci API, kuota, dan hasil seleksi terakhir. Semua angka diperbarui setiap kali sesi berjalan.",
        tips: [
          "Pastikan kunci API sudah terverifikasi sebelum memulai.",
          "Perhatikan sisa kuota agar seleksi tidak terhenti.",
        ],
      },
      {
        selector: '[data-tour="ps-subnav"]',
        kicker: "Halaman ini · Menu",
        title: "Menu ruang seleksi",
        body:
          "Berpindah antara Ringkasan, Mulai seleksi, Skill, Pengaturan, dan Riwayat.",
        tips: [
          "Atur skill dan kuota sebelum seleksi pertama.",
          "Buka Riwayat untuk meninjau sesi sebelumnya.",
        ],
      },
      {
        selector: '[data-tour="ps-start"]',
        kicker: "Halaman ini · Mulai",
        title: "Formulir seleksi",
        body:
          "Pilih skill, unggah foto, atur target dan ambang skor, lalu jalankan agen seleksi.",
        tips: [
          "Gunakan foto beresolusi cukup dan pencahayaan baik.",
          "Isi target 0 bila ingin memilih semua foto yang layak.",
          "Tambahkan konteks kegiatan agar penilaian lebih tepat.",
        ],
      },
      {
        selector: '[data-tour="ps-run-hero"]',
        kicker: "Halaman ini · Proses",
        title: "Status sesi seleksi",
        body:
          "Pantau progres, jumlah foto dipilih, cadangan, ditolak, dan permintaan AI yang terpakai.",
        tips: [
          "Sesi dapat dijeda otomatis saat kuota penuh.",
          "Gunakan Lanjutkan seleksi setelah kuota tersedia.",
        ],
      },
      {
        selector: '[data-tour="ps-results"]',
        kicker: "Halaman ini · Hasil",
        title: "Hasil penilaian foto",
        body:
          "Setiap kartu memuat skor, alasan, tag, dan keputusan awal. Anda dapat mengubah keputusan sebelum menyimpan.",
        tips: [
          "Gunakan tab filter untuk fokus pada foto dipilih atau ditolak.",
          "Baca alasan dan kelemahan sebelum mengubah keputusan.",
          "Klik Simpan perubahan agar keputusan manual tersimpan.",
        ],
      },
      {
        selector: '[data-tour="ps-apply"]',
        kicker: "Halaman ini · Terapkan",
        title: "Terapkan ke kegiatan",
        body:
          "Pilih kegiatan tujuan, lalu terapkan foto terpilih. Anda juga dapat mengunduh ZIP atau membagikan pilihan.",
        tips: [
          "Pastikan kegiatan tujuan sudah benar sebelum menerapkan.",
          "Gunakan unduh ZIP untuk arsip di luar aplikasi.",
        ],
      },
    ],
    activities: [
      {
        selector: '[data-tour="activities-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Filter dokumentasi",
        body:
          "Gabungkan kata kunci, komisi, kategori, lokasi, tanggal, dan status untuk menemukan kegiatan yang tepat.",
        tips: [
          "Buka Filter lanjutan untuk lokasi, tanggal, dan status.",
          "Gunakan Reset untuk menghapus semua filter.",
        ],
      },
      {
        selector: '[data-tour="activities-meta"]',
        kicker: "Halaman ini · Hasil",
        title: "Ringkasan hasil dan ekspor",
        body:
          "Bagian ini menunjukkan jumlah hasil, filter aktif, dan tombol Ekspor CSV sesuai filter yang dipakai.",
        tips: [
          "Periksa filter aktif sebelum mengekspor.",
          "Gunakan ekspor untuk laporan kegiatan ke pimpinan.",
        ],
      },
      {
        selector: '[data-tour="activities-grid"]',
        kicker: "Halaman ini · Kartu kegiatan",
        title: "Daftar kegiatan",
        body:
          "Setiap kartu memuat sampul, judul, tanggal, lokasi, komisi, dan status. Klik untuk membuka detail kegiatan.",
        tips: [
          "Perhatikan status draf atau terbit sebelum bertindak.",
          "Gunakan tombol Unggah di bilah atas untuk menambah kegiatan.",
        ],
      },
    ],
    search: [
      {
        selector: '[data-tour="search-hero"]',
        kicker: "Halaman ini · Pencarian",
        title: "Dua cara menemukan dokumentasi",
        body:
          "Tab di bagian atas memisahkan pencarian teks dan pencarian wajah. Pilih metode sesuai informasi yang Anda miliki.",
        tips: [
          "Gunakan Teks & nama bila tahu nama, jabatan, atau lokasi.",
          "Gunakan Wajah bila hanya memiliki foto.",
        ],
      },
      {
        selector: '[data-tour="search-text"]',
        kicker: "Halaman ini · Teks",
        title: "Pencarian teks dan filter",
        body:
          "Kata kunci, komisi, kategori, lokasi, dan rentang tanggal dapat digabungkan untuk hasil yang presisi.",
        tips: [
          "Buka Filter lanjutan untuk kriteria tambahan.",
          "Kosongkan filter untuk melihat hasil yang lebih luas.",
        ],
      },
      {
        selector: '[data-tour="search-face"]',
        kicker: "Halaman ini · Wajah",
        title: "Unggah foto wajah",
        body:
          "Unggah foto frontal, pilih tingkat kemiripan, lalu jalankan pencarian. Hasil menampilkan skor kecocokan yang tetap perlu diverifikasi.",
        tips: [
          "Gunakan foto dengan wajah jelas dan tidak terpotong.",
          "Tingkat seimbang disarankan untuk hasil terbaik.",
          "Periksa hasil sebelum memakainya sebagai bukti.",
        ],
      },
      {
        selector: '[data-tour="search-results"]',
        kicker: "Halaman ini · Hasil",
        title: "Hasil pencarian",
        body:
          "Kartu hasil menampilkan kegiatan, komisi, tanggal, dan kecocokan wajah. Gunakan hasil sebagai petunjuk awal.",
        tips: [
          "Buka detail kegiatan untuk melihat konteks lengkap.",
          "Verifikasi hasil wajah secara manusiawi.",
        ],
      },
    ],
    members: [
      {
        selector: '[data-tour="members-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Cari anggota dewan",
        body:
          "Gunakan nama, komisi, dan status untuk mempersempit direktori anggota.",
        tips: [
          "Kosongkan kata kunci untuk menampilkan semua anggota.",
          "Gunakan Reset bila hasil terlalu sempit.",
        ],
      },
      {
        selector: '[data-tour="members-meta"]',
        kicker: "Halaman ini · Hasil",
        title: "Ringkasan direktori",
        body:
          "Menampilkan jumlah anggota yang cocok dan pengingat bahwa wajah terdaftar memungkinkan pencarian otomatis.",
        tips: [
          "Periksa jumlah hasil sebelum membuka profil.",
          "Gunakan status untuk memisahkan anggota aktif.",
        ],
      },
      {
        selector: '[data-tour="members-grid"]',
        kicker: "Halaman ini · Kartu anggota",
        title: "Direktori anggota",
        body:
          "Setiap kartu memuat foto, jabatan, komisi, daerah pemilihan, dan status Face ID.",
        tips: [
          "Klik kartu untuk membuka profil lengkap.",
          "Administrator dapat menambah anggota dari bilah atas.",
        ],
      },
    ],
    commissions: [
      {
        selector: '[data-tour="commissions-intro"]',
        kicker: "Halaman ini · Pengantar",
        title: "Komisi dan bidang kerja",
        body:
          "Ringkasan ini menjelaskan bahwa setiap komisi membidangi ruang lingkup tertentu dan menjadi acuan pengelompokan dokumentasi.",
        tips: [
          "Gunakan jumlah komisi aktif sebagai indikator cakupan.",
          "Pilih komisi untuk melihat anggota dan kegiatannya.",
        ],
      },
      {
        selector: '[data-tour="commissions-list"]',
        kicker: "Halaman ini · Daftar",
        title: "Daftar komisi",
        body:
          "Setiap baris menampilkan lambang, nama, bidang, jumlah anggota, dan dokumentasi terkait.",
        tips: [
          "Klik baris komisi untuk membuka detail.",
          "Perhatikan warna aksen yang konsisten di seluruh aplikasi.",
        ],
      },
    ],
    releases: [
      {
        selector: '[data-tour="releases-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Cari siaran pers",
        body:
          "Filter rilis berdasarkan kata kunci, status, rilis milik Anda, dan rentang tanggal.",
        tips: [
          "Centang Rilis saya untuk fokus pada karya sendiri.",
          "Gunakan Reset untuk kembali ke semua rilis.",
        ],
      },
      {
        selector: '[data-tour="releases-stats"]',
        kicker: "Halaman ini · Angka kunci",
        title: "Statistik rilis",
        body:
          "Ringkasan jumlah rilis terbit, draf, arsip, dan hasil filter saat ini.",
        tips: [
          "Bandingkan draf dan terbit untuk mengukur ketuntasan.",
          "Gunakan angka hasil filter untuk memastikan pencarian tepat.",
        ],
      },
      {
        selector: '[data-tour="releases-grid"]',
        kicker: "Halaman ini · Kartu rilis",
        title: "Daftar rilis",
        body:
          "Setiap kartu memuat kode, judul, ringkasan, tag, status, dan tautan baca. Pengelola konten dapat langsung menyunting.",
        tips: [
          "Buka rilis untuk membaca naskah lengkap.",
          "Gunakan Tulis rilis di bilah atas untuk membuat rilis baru.",
        ],
      },
    ],
    sentiment: [
      {
        selector: '[data-tour="sentiment-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Cari anggota dan komisi",
        body:
          "Cari nama anggota atau pilih komisi untuk menampilkan ringkasan sentimen pemberitaan.",
        tips: [
          "Kosongkan filter untuk melihat semua anggota.",
          "Gunakan Reset untuk kembali ke tampilan awal.",
        ],
      },
      {
        selector: '[data-tour="sentiment-meta"]',
        kicker: "Halaman ini · Catatan",
        title: "Cara membaca sentimen",
        body:
          "Sentimen dinilai dari judul dan kutipan berita, bukan penilaian resmi lembaga. Panel ini juga menandai bila Gemini belum dikonfigurasi.",
        tips: [
          "Gunakan hasil sebagai indikator awal.",
          "Buka pemberitaan untuk membaca konteks lengkap.",
        ],
      },
      {
        selector: '[data-tour="sentiment-table"]',
        kicker: "Halaman ini · Tabel",
        title: "Tabel sentimen per anggota",
        body:
          "Tabel menampilkan gauge, jumlah berita, sebaran positif-netral-negatif, status pemindaian, dan aksi cepat.",
        tips: [
          "Klik ikon daftar untuk membaca semua pemberitaan.",
          "Ikon bagan membuka dashboard anggota.",
          "Gunakan ikon Refresh untuk memindai berita terbaru.",
        ],
      },
    ],
    users: [
      {
        selector: '[data-tour="users-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Cari pengguna",
        body:
          "Filter akun berdasarkan nama, peran, dan status aktif.",
        tips: [
          "Gunakan peran untuk memeriksa akses tertentu.",
          "Reset filter untuk melihat seluruh pengguna.",
        ],
      },
      {
        selector: '[data-tour="users-meta"]',
        kicker: "Halaman ini · Hasil",
        title: "Ringkasan pengguna",
        body:
          "Menampilkan jumlah akun yang cocok dan pengingat bahwa peran menentukan akses.",
        tips: [
          "Periksa peran sebelum mengubah akun.",
          "Gunakan status untuk menemukan akun nonaktif.",
        ],
      },
      {
        selector: '[data-tour="users-table"]',
        kicker: "Halaman ini · Tabel",
        title: "Tabel pengguna dan aksi",
        body:
          "Setiap baris memuat identitas, peran, status, dan aksi sunting, reset kata sandi, serta aktif/nonaktif.",
        tips: [
          "Nonaktifkan akun yang tidak lagi bertugas.",
          "Reset kata sandi hanya bila pengguna kehilangan akses.",
        ],
      },
      {
        selector: '[data-tour="users-policy"]',
        kicker: "Halaman ini · Kebijakan",
        title: "Kebijakan akun",
        body:
          "Akun baru wajib mengganti kata sandi saat pertama masuk. Akun nonaktif tidak dapat login dan sesinya berakhir.",
        tips: [
          "Tinjau kebijakan ini sebelum memberi akses baru.",
          "Buka log audit untuk memantau perubahan akun.",
        ],
      },
    ],
    audit: [
      {
        selector: '[data-tour="audit-filter"]',
        kicker: "Halaman ini · Filter",
        title: "Telusuri jejak audit",
        body:
          "Filter berdasarkan kata kunci, jenis aksi, dan rentang tanggal untuk menemukan peristiwa tertentu.",
        tips: [
          "Gunakan jenis aksi untuk mempersempit hasil.",
          "Reset filter untuk melihat semua peristiwa.",
        ],
      },
      {
        selector: '[data-tour="audit-meta"]',
        kicker: "Halaman ini · Hasil",
        title: "Ringkasan dan ekspor",
        body:
          "Bagian ini menunjukkan jumlah peristiwa dan menegaskan bahwa log tidak dapat diubah atau dihapus.",
        tips: [
          "Ekspor CSV bila laporan perlu diserahkan.",
          "Periksa jumlah hasil sebelum menelusuri kronologi.",
        ],
      },
      {
        selector: '[data-tour="audit-table"]',
        kicker: "Halaman ini · Tabel",
        title: "Tabel peristiwa",
        body:
          "Setiap baris memuat waktu, aktor, aksi, ringkasan, dan alamat IP. Warna badge membantu membedakan aksi penting.",
        tips: [
          "Periksa kronologi sebelum mengambil tindakan.",
          "Gunakan detail aktor untuk menelusuri perubahan terkait.",
        ],
      },
      {
        selector: '[data-tour="audit-policy"]',
        kicker: "Halaman ini · Retensi",
        title: "Tentang log audit",
        body:
          "Semua tindakan penting dicatat lengkap dengan waktu, aktor, dan alamat IP, lalu disimpan secara permanen.",
        tips: [
          "Gunakan log untuk investigasi dan kepatuhan.",
          "Jangan bagikan data audit ke pihak yang tidak berwenang.",
        ],
      },
    ],
    profile: [
      {
        selector: '[data-tour="profile-hero"]',
        kicker: "Halaman ini · Profil",
        title: "Identitas akun",
        body:
          "Kartu ini menampilkan nama, peran, komisi, waktu masuk terakhir, dan status keamanan akun.",
        tips: [
          "Pastikan nama dan peran sudah benar.",
          "Perhatikan penanda wajib ganti kata sandi.",
        ],
      },
      {
        selector: '[data-tour="profile-identity"]',
        kicker: "Halaman ini · Identitas",
        title: "Data identitas",
        body:
          "Nama dan email tampil pada jejak audit dan dokumen internal. Perbarui bila ada perubahan.",
        tips: [
          "Gunakan email resmi agar jejak audit mudah ditelusuri.",
          "Simpan setelah selesai mengubah data.",
        ],
      },
      {
        selector: '[data-tour="profile-password"]',
        kicker: "Halaman ini · Keamanan",
        title: "Ganti kata sandi",
        body:
          "Gunakan minimal 10 karakter dengan huruf besar, huruf kecil, angka, dan simbol.",
        tips: [
          "Ganti kata sandi secara berkala.",
          "Jangan gunakan kata sandi yang sama dengan layanan lain.",
        ],
      },
      {
        selector: '[data-tour="profile-token"]',
        kicker: "Halaman ini · API",
        title: "Token API",
        body:
          "Token baru hanya ditampilkan sekali. Gunakan header Authorization Bearer untuk integrasi.",
        tips: [
          "Simpan token di tempat aman.",
          "Cabut token yang tidak lagi digunakan.",
        ],
      },
      {
        selector: '[data-tour="profile-activity"]',
        kicker: "Halaman ini · Aktivitas",
        title: "Aktivitas akun",
        body:
          "Sepuluh peristiwa terakhir yang tercatat atas nama Anda membantu memantau penggunaan akun.",
        tips: [
          "Periksa aktivitas yang tidak Anda kenali.",
          "Hubungi administrator bila ada kejanggalan.",
        ],
      },
    ],
    member_dashboard: [
      {
        selector: '[data-tour="member-dash-hero"]',
        kicker: "Halaman ini · Identitas",
        title: "Kartu anggota dewan",
        body:
          "Kartu ini memuat foto, jabatan, komisi, daerah pemilihan, status Face ID, dan angka kegiatan Anda.",
        tips: [
          "Periksa status Face ID untuk memastikan login wajah aktif.",
          "Gunakan tombol Cetak untuk membagikan ringkasan.",
        ],
      },
      {
        selector: '[data-tour="member-dash-sentiment"]',
        kicker: "Halaman ini · Sentimen",
        title: "Sentimen pemberitaan",
        body:
          "Gauge dan bilah menunjukkan sebaran positif, netral, dan negatif. Daftar berita di bawahnya memberi konteks.",
        tips: [
          "Gunakan hasil sebagai indikator awal.",
          "Buka artikel untuk membaca konteks lengkap.",
        ],
      },
      {
        selector: '[data-tour="member-dash-publication"]',
        kicker: "Halaman ini · Publikasi",
        title: "Publikasi dan dokumentasi Humas",
        body:
          "Ringkasan ini menunjukkan kegiatan tertaut, yang sudah terbit, unggahan Humas, dan aktivitas 90 hari terakhir.",
        tips: [
          "Buka dokumentasi untuk melihat foto dan detail kegiatan.",
          "Gunakan angka ini untuk menilai keterlibatan Anda.",
        ],
      },
      {
        selector: '[data-tour="member-dash-trend"]',
        kicker: "Halaman ini · Tren",
        title: "Tren dokumentasi",
        body:
          "Grafik batang memperlihatkan ritme kegiatan Anda selama enam bulan terakhir.",
        tips: [
          "Gunakan tren untuk melihat periode paling aktif.",
          "Klik Telusuri untuk membuka dokumentasi terkait.",
        ],
      },
      {
        selector: '[data-tour="member-dash-recent"]',
        kicker: "Halaman ini · Dokumentasi",
        title: "Dokumentasi terbaru",
        body:
          "Kartu kegiatan menampilkan dokumentasi terbaru yang melibatkan Anda.",
        tips: [
          "Klik kartu untuk membuka detail kegiatan.",
          "Gunakan Lihat semua untuk menelusuri arsip lengkap.",
        ],
      },
      {
        selector: '[data-tour="member-dash-faceid"]',
        kicker: "Halaman ini · Keamanan",
        title: "Face ID login",
        body:
          "Panel ini menunjukkan status wajah dan akun login yang tertaut. Data wajah disimpan sebagai encoding biometrik.",
        tips: [
          "Daftarkan wajah dari halaman login bila belum aktif.",
          "Administrator dapat menghapus Face ID bila diperlukan.",
        ],
      },
      {
        selector: '[data-tour="member-dash-duties"]',
        kicker: "Halaman ini · Tugas",
        title: "Tugas dan fungsi dewan",
        body:
          "Daftar ini mengingatkan peran anggota dewan dalam fungsi legislasi, anggaran, dan pengawasan.",
        tips: [
          "Gunakan daftar sebagai acuan kegiatan.",
          "Sesuaikan prioritas dengan arahan pimpinan.",
        ],
      },
    ],
    drive: [
      {
        selector: '[data-tour="drive-switch"]',
        kicker: "Halaman ini · Drive",
        title: "Drive pribadi dan Drive tim",
        body:
          "Tab di atas memisahkan berkas pribadi dan berkas bersama. Administrator juga dapat membuka Drive staf lain.",
        tips: [
          "Gunakan Drive tim untuk template dan aset bersama.",
          "Berkas pribadi tidak pernah muncul di Drive tim.",
        ],
      },
      {
        selector: '[data-tour="drive-quota"]',
        kicker: "Halaman ini · Kuota",
        title: "Pemakaian ruang",
        body:
          "Bilah kuota menunjukkan ruang terpakai, sisa, dan peringatan bila hampir penuh.",
        tips: [
          "Hapus berkas yang tidak dipakai bila ruang menipis.",
          "Periksa sisa ruang sebelum mengunggah berkas besar.",
        ],
      },
      {
        selector: '[data-tour="drive-toolbar"]',
        kicker: "Halaman ini · Navigasi",
        title: "Remah folder dan pencarian",
        body:
          "Gunakan remah folder untuk kembali dan kolom pencarian untuk menemukan nama berkas di seluruh Drive.",
        tips: [
          "Klik nama folder untuk masuk.",
          "Gunakan Reset untuk menghapus kata kunci.",
        ],
      },
      {
        selector: '[data-tour="drive-tools"]',
        kicker: "Halaman ini · Berkas",
        title: "Unggah dan kelola berkas",
        body:
          "Unggah beberapa berkas sekaligus, buat folder baru, ubah nama, unduh, atau hapus dari panel ini.",
        tips: [
          "Maksimal 100 MB per berkas dan tidak melebihi sisa kuota.",
          "Gunakan unduh untuk mengambil berkas langsung dari CDN.",
        ],
      },
    ],
  };

  const DETAIL_STEPS = [
    {
      test: /^\/kegiatan\/\d+$/,
      steps: [
        {
          selector: '[data-tour="activity-hero"]',
          kicker: "Halaman ini · Detail",
          title: "Identitas kegiatan",
          body:
            "Hero menampilkan kode, judul, status, kategori, tanggal, lokasi, dan komisi terkait.",
          tips: [
            "Periksa status sebelum menerbitkan atau mengarsipkan.",
            "Gunakan breadcrumb untuk kembali ke daftar.",
          ],
        },
        {
          selector: '[data-tour="activity-actions"]',
          kicker: "Halaman ini · Aksi",
          title: "Aksi dokumentasi",
          body:
            "Dari sini Anda dapat menyunting, menerbitkan, mengarsipkan, mencetak, menyalin tautan, dan mengelola foto.",
          tips: [
            "Aksi yang tersedia mengikuti peran dan status kegiatan.",
            "Konfirmasi tindakan yang berdampak sebelum melanjutkan.",
          ],
        },
        {
          selector: '[data-tour="activity-description"]',
          kicker: "Halaman ini · Deskripsi",
          title: "Deskripsi kegiatan",
          body:
            "Deskripsi membantu pencarian teks dan memberi konteks kepada pembaca dokumentasi.",
          tips: [
            "Pastikan deskripsi menjelaskan tujuan dan hasil kegiatan.",
            "Perbaiki bila ada informasi yang kurang tepat.",
          ],
        },
        {
          selector: '[data-tour="activity-gallery"]',
          kicker: "Halaman ini · Galeri",
          title: "Galeri dokumentasi",
          body:
            "Galeri menampilkan foto, kotak wajah, jumlah wajah terdeteksi, dan aksi proses ulang atau hapus.",
          tips: [
            "Aktifkan Kotak wajah untuk melihat posisi deteksi.",
            "Klik foto untuk memperbesar.",
          ],
        },
        {
          selector: '[data-tour="activity-face-review"]',
          kicker: "Halaman ini · Deteksi",
          title: "Tinjauan deteksi wajah",
          body:
            "Setiap deteksi dapat dikonfirmasi ke anggota yang tepat atau ditolak bila bukan orang yang sesuai.",
          tips: [
            "Verifikasi nama sebelum mengonfirmasi.",
            "Tolak deteksi yang meragukan agar data tetap bersih.",
          ],
        },
        {
          selector: '[data-tour="activity-upload"]',
          kicker: "Halaman ini · Unggah",
          title: "Tambah foto",
          body:
            "Unggah foto baru langsung dari halaman detail. Sistem mendeteksi wajah secara otomatis.",
          tips: [
            "Patuhi batas jumlah dan ukuran foto.",
            "Gunakan foto beresolusi baik agar deteksi akurat.",
          ],
        },
        {
          selector: '[data-tour="activity-side"]',
          kicker: "Halaman ini · Samping",
          title: "Anggota dan konteks",
          body:
            "Panel samping merangkum anggota tertaut, komisi, dan konteks lain yang membantu verifikasi.",
          tips: [
            "Periksa anggota tertaut sebelum menerbitkan.",
            "Gunakan tautan anggota untuk membuka profil.",
          ],
        },
      ],
    },
    {
      test: /^\/kegiatan\/(baru|\d+\/edit)$/,
      steps: [
        {
          selector: '[data-tour="activity-form-main"]',
          kicker: "Formulir · Informasi",
          title: "Metadata kegiatan",
          body:
            "Isi judul, kategori, tanggal, waktu, lokasi, dan deskripsi. Metadata ini menjadi dasar pencarian dan laporan.",
          tips: [
            "Gunakan judul resmi seperti pada undangan.",
            "Lengkapi deskripsi agar pencarian lebih akurat.",
          ],
        },
        {
          selector: '[data-tour="activity-form-commission"]',
          kicker: "Formulir · Komisi",
          title: "Komisi terkait",
          body:
            "Pilih satu atau lebih komisi yang terlibat agar dokumentasi terkelompok dengan benar.",
          tips: [
            "Pilih komisi sesuai bidang kegiatan.",
            "Komisi menentukan penelusuran di halaman komisi.",
          ],
        },
        {
          selector: '[data-tour="activity-form-photos"]',
          kicker: "Formulir · Foto",
          title: "Foto dokumentasi",
          body:
            "Unggah foto JPG, PNG, atau WEBP. Deteksi wajah berjalan otomatis setelah foto tersimpan.",
          tips: [
            "Perhatikan batas jumlah dan ukuran foto.",
            "Gunakan foto yang jelas untuk hasil deteksi terbaik.",
          ],
        },
        {
          selector: '[data-tour="activity-form-actions"]',
          kicker: "Formulir · Simpan",
          title: "Simpan kegiatan",
          body:
            "Simpan sebagai draf atau terbitkan sesuai alur. Periksa kembali seluruh isian sebelum menyimpan.",
          tips: [
            "Gunakan Batal untuk kembali tanpa menyimpan.",
            "Lengkapi foto sebelum menerbitkan.",
          ],
        },
      ],
    },
    {
      test: /^\/anggota\/\d+$/,
      steps: [
        {
          selector: '[data-tour="member-hero"]',
          kicker: "Halaman ini · Profil",
          title: "Identitas anggota",
          body:
            "Hero menampilkan foto, jabatan, komisi, partai, dapil, kontak, status wajah, dan Face ID.",
          tips: [
            "Periksa status wajah sebelum mencari dokumentasi.",
            "Gunakan aksi cepat untuk membuka dashboard atau pencarian.",
          ],
        },
        {
          selector: '[data-tour="member-bio"]',
          kicker: "Halaman ini · Biodata",
          title: "Profil dan metadata",
          body:
            "Bagian ini memuat bio singkat serta metadata komisi, partai, dapil, dan persetujuan biometrik.",
          tips: [
            "Pastikan data keanggotaan sudah benar.",
            "Perbarui bio bila ada informasi baru.",
          ],
        },
        {
          selector: '[data-tour="member-activities"]',
          kicker: "Halaman ini · Dokumentasi",
          title: "Kegiatan tertaut",
          body:
            "Kartu kegiatan menampilkan dokumentasi yang melibatkan anggota ini.",
          tips: [
            "Buka kegiatan untuk melihat foto dan deteksi wajah.",
            "Gunakan Lihat semua untuk menelusuri arsip.",
          ],
        },
        {
          selector: '[data-tour="member-sentiment"]',
          kicker: "Halaman ini · Sentimen",
          title: "Sentimen pemberitaan",
          body:
            "Gauge dan bilah merangkum pemberitaan positif, netral, dan negatif terkait anggota.",
          tips: [
            "Gunakan hasil sebagai indikator awal.",
            "Buka semua pemberitaan untuk konteks lengkap.",
          ],
        },
        {
          selector: '[data-tour="member-faces"]',
          kicker: "Halaman ini · Wajah",
          title: "Data wajah",
          body:
            "Panel ini menampilkan encoding wajah dan formulir penambahan foto. Data disimpan sebagai encoding, bukan foto mentah.",
          tips: [
            "Tambahkan variasi sudut dan pencahayaan untuk akurasi.",
            "Hapus encoding yang tidak valid bila perlu.",
          ],
        },
        {
          selector: '[data-tour="member-faceid"]',
          kicker: "Halaman ini · Face ID",
          title: "Face ID login",
          body:
            "Status Face ID dan akun login yang tertaut ditampilkan di sini. Administrator dapat menghapusnya.",
          tips: [
            "Anggota dapat mendaftar ulang dari halaman login.",
            "Periksa status sebelum membantu proses login.",
          ],
        },
      ],
    },
    {
      test: /^\/anggota\/\d+\/sentimen$/,
      steps: [
        {
          selector: '[data-tour="member-sentiment-summary"]',
          kicker: "Halaman ini · Ringkasan",
          title: "Ringkasan sentimen anggota",
          body:
            "Gauge, sebaran sentimen, topik, dan tren pemberitaan dirangkum di bagian atas.",
          tips: [
            "Gunakan ringkasan untuk membaca kondisi umum.",
            "Perhatikan tanggal pembaruan terakhir.",
          ],
        },
        {
          selector: '[data-tour="member-sentiment-actions"]',
          kicker: "Halaman ini · Pemindaian",
          title: "Pindai berita terbaru",
          body:
            "Jalankan pemindaian untuk memperbarui pemberitaan. Tombol nonaktif bila Tavily belum dikonfigurasi.",
          tips: [
            "Pemindaian memakai Tavily dan Gemini.",
            "Baca catatan bila pemindaian terakhir gagal.",
          ],
        },
        {
          selector: '[data-tour="member-sentiment-filter"]',
          kicker: "Halaman ini · Filter",
          title: "Filter pemberitaan",
          body:
            "Cari berita berdasarkan kata kunci dan sentimen positif, netral, atau negatif.",
          tips: [
            "Gunakan Reset untuk kembali ke semua berita.",
            "Filter sentimen membantu menemukan isu tertentu.",
          ],
        },
        {
          selector: '[data-tour="member-sentiment-list"]',
          kicker: "Halaman ini · Daftar",
          title: "Daftar pemberitaan",
          body:
            "Setiap item memuat sumber, judul, kutipan, sentimen, skor, dan tautan artikel.",
          tips: [
            "Buka artikel untuk memverifikasi konteks.",
            "Gunakan skor sebagai indikator awal, bukan penilaian resmi.",
          ],
        },
      ],
    },
    {
      test: /^\/komisi\/\d+$/,
      steps: [
        {
          selector: '[data-tour="commission-hero"]',
          kicker: "Halaman ini · Komisi",
          title: "Profil komisi",
          body:
            "Hero menampilkan nama, bidang, deskripsi, dan angka anggota, dokumentasi, serta staf komisi.",
          tips: [
            "Periksa bidang komisi untuk konteks dokumentasi.",
            "Gunakan tautan direktori untuk melihat anggota.",
          ],
        },
        {
          selector: '[data-tour="commission-members"]',
          kicker: "Halaman ini · Anggota",
          title: "Anggota komisi",
          body:
            "Kartu anggota menampilkan foto, jabatan, dan status wajah.",
          tips: [
            "Klik kartu untuk membuka profil anggota.",
            "Gunakan direktori untuk pencarian lebih luas.",
          ],
        },
        {
          selector: '[data-tour="commission-activities"]',
          kicker: "Halaman ini · Dokumentasi",
          title: "Kegiatan komisi",
          body:
            "Kartu kegiatan menampilkan dokumentasi terbaru yang terkait dengan komisi ini.",
          tips: [
            "Buka kegiatan untuk melihat galeri dan deteksi wajah.",
            "Gunakan Lihat semua untuk menelusuri arsip komisi.",
          ],
        },
        {
          selector: '[data-tour="commission-staff"]',
          kicker: "Halaman ini · Staf",
          title: "Staf komisi",
          body:
            "Tabel ini menampilkan pengguna dengan akses staf pada komisi tersebut.",
          tips: [
            "Periksa peran sebelum mengubah akses.",
            "Hubungi administrator bila ada staf yang tidak sesuai.",
          ],
        },
        {
          selector: '[data-tour="commission-edit"]',
          kicker: "Halaman ini · Pengaturan",
          title: "Sunting profil komisi",
          body:
            "Administrator dapat mengubah nama, bidang, deskripsi, dan warna aksen komisi.",
          tips: [
            "Perubahan berlaku di seluruh halaman komisi.",
            "Gunakan warna yang konsisten dengan identitas komisi.",
          ],
        },
      ],
    },
    {
      test: /^\/rilis\/\d+$/,
      steps: [
        {
          selector: '[data-tour="release-content"]',
          kicker: "Halaman ini · Rilis",
          title: "Naskah siaran pers",
          body:
            "Artikel ini memuat judul, ringkasan, penulis, tanggal, isi, tag, dan tautan kegiatan terkait.",
          tips: [
            "Periksa kode dan status sebelum menerbitkan.",
            "Gunakan tautan kegiatan untuk membuka konteks dokumentasi.",
          ],
        },
        {
          selector: '[data-tour="release-actions"]',
          kicker: "Halaman ini · Aksi",
          title: "Terbitkan dan kelola rilis",
          body:
            "Aksi mencakup cetak, salin tautan, terbitkan, arsipkan, pulihkan, dan hapus sesuai peran.",
          tips: [
            "Konfirmasi tindakan yang berdampak permanen.",
            "Gunakan arsip untuk menyimpan referensi tanpa menampilkan rilis.",
          ],
        },
        {
          selector: '[data-tour="release-side"]',
          kicker: "Halaman ini · Samping",
          title: "Metadata rilis",
          body:
            "Panel samping merangkum penulis, tanggal rilis, waktu terbit, dan pembaruan terakhir.",
          tips: [
            "Periksa tanggal sebelum membagikan rilis.",
            "Gunakan data ini untuk laporan publikasi.",
          ],
        },
        {
          selector: '[data-tour="release-related"]',
          kicker: "Halaman ini · Terkait",
          title: "Kegiatan dan rilis lain",
          body:
            "Tautan ke kegiatan terkait dan rilis lain membantu pembaca menelusuri konteks publikasi.",
          tips: [
            "Buka kegiatan untuk melihat dokumentasi foto.",
            "Gunakan rilis lain sebagai referensi gaya penulisan.",
          ],
        },
      ],
    },
    {
      test: /^\/rilis\/(baru|\d+\/edit)$/,
      steps: [
        {
          selector: '[data-tour="release-form-main"]',
          kicker: "Formulir · Naskah",
          title: "Susun siaran pers",
          body:
            "Isi judul, tanggal, ringkasan, isi, tag, dan kegiatan terkait. Ringkasan minimal 40 karakter.",
          tips: [
            "Awali judul dengan subjek utama.",
            "Pisahkan paragraf dengan satu baris kosong.",
          ],
        },
        {
          selector: '[data-tour="release-form-side"]',
          kicker: "Formulir · Panduan",
          title: "Panduan penulisan",
          body:
            "Panel samping mengingatkan struktur rilis: judul jelas, teras berita, kutipan, dan tautan kegiatan.",
          tips: [
            "Gunakan fakta dan angka yang akurat.",
            "Tautkan rilis ke kegiatan agar konteks lengkap.",
          ],
        },
      ],
    },
    {
      test: /^\/pengguna\/(baru|\d+\/edit)$/,
      steps: [
        {
          selector: '[data-tour="user-form-identity"]',
          kicker: "Formulir · Identitas",
          title: "Identitas pengguna",
          body:
            "Isi nama, email, dan kata sandi awal. Pengguna wajib mengganti kata sandi saat pertama masuk.",
          tips: [
            "Gunakan email resmi.",
            "Kata sandi minimal 10 karakter.",
          ],
        },
        {
          selector: '[data-tour="user-form-role"]',
          kicker: "Formulir · Akses",
          title: "Peran dan komisi",
          body:
            "Peran menentukan halaman dan tindakan yang dapat dilakukan. Staf komisi wajib memilih komisi.",
          tips: [
            "Berikan akses sesuai kebutuhan tugas.",
            "Tinjau akses secara berkala melalui log audit.",
          ],
        },
        {
          selector: '[data-tour="user-form-policy"]',
          kicker: "Formulir · Kebijakan",
          title: "Prinsip akses minimal",
          body:
            "Panel ini menjelaskan batas akses tiap peran agar data dewan tetap terlindungi.",
          tips: [
            "Hindari memberikan peran administrator tanpa kebutuhan.",
            "Catat alasan perubahan akses.",
          ],
        },
      ],
    },
    {
      test: /^\/(staf-humas|dashboard-staf)\/\d+$/,
      steps: [
        {
          selector: '[data-tour="humas-hero"]',
          kicker: "Halaman ini · Staf",
          title: "Profil staf Humas",
          body:
            "Hero menampilkan foto, jabatan, unit, status Face ID, dan angka unggahan staf.",
          tips: [
            "Periksa status Face ID sebelum membantu login.",
            "Gunakan aksi cepat untuk membuka ruang kerja.",
          ],
        },
        {
          selector: '[data-tour="humas-shortcuts"]',
          kicker: "Halaman ini · Ruang kerja",
          title: "Ruang kerja staf",
          body:
            "Bagian ini merangkum pintasan, draf, rilis, publikasi, dan tren unggahan staf.",
          tips: [
            "Gunakan pintasan untuk memahami alur kerja staf.",
            "Periksa draf yang perlu diselesaikan.",
          ],
        },
        {
          selector: '[data-tour="humas-faceid"]',
          kicker: "Halaman ini · Keamanan",
          title: "Face ID staf",
          body:
            "Panel ini menunjukkan status wajah dan akun login staf. Administrator dapat menghapus Face ID.",
          tips: [
            "Penghapusan memaksa staf mendaftar ulang.",
            "Data wajah disimpan sebagai encoding biometrik.",
          ],
        },
      ],
    },
  ];

  function detailStepsFor(path) {
    for (const entry of DETAIL_STEPS) {
      if (entry.test.test(path)) return entry.steps;
    }
    return [];
  }

  const steps = [];

  function navLabel(el) {
    const label = el.querySelector(".nav-label");
    return (label ? label.textContent : el.textContent || "").trim();
  }

  function firstVisible(selectors) {
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (isVisible(el)) return el;
    }
    return null;
  }

  function buildSteps() {
    steps.push({
      kicker: "Asisten SIDEWA",
      title: "Mengenal SIDEWA",
      body:
        "Saya akan memandu Anda mengenali seluruh antarmuka SIDEWA: bilah atas, isi halaman, ikon fitur, dan sidebar. Setiap langkah menyorot elemen yang sedang dijelaskan.",
      tips: [
        "Gunakan tombol Berikutnya atau tombol panah untuk berpindah langkah.",
        "Tekan Esc kapan saja untuk menutup panduan.",
        "Nyalakan narasi suara bila ingin penjelasan dibacakan.",
        "Di ponsel, panduan tampil sebagai panel bawah yang bisa diperluas.",
      ],
      target: null,
    });

    /* Bilah atas dan ikon aksi cepat. */
    const topbar = firstVisible(['[data-tour="topbar"]', ".topbar"]);
    if (topbar) {
      steps.push({
        kicker: "Navigasi · Bilah atas",
        title: "Judul halaman dan aksi cepat",
        body:
          "Bilah atas menampilkan judul halaman, pencarian, tombol unggah, peran akun, dan foto profil. Ikon di sini selalu tersedia di halaman mana pun.",
        tips: [
          "Judul dan subjudul menjelaskan halaman yang sedang dibuka.",
          "Aksi di kanan mengikuti peran dan kewenangan Anda.",
        ],
        target: topbar,
      });
    }

    const topbarSearch = firstVisible(['[data-tour="topbar-search"]']);
    if (topbarSearch) {
      steps.push({
        kicker: "Ikon fitur · Pencarian",
        title: "Ikon pencarian",
        body:
          "Ikon kaca pembesar membuka halaman pencarian wajah dan teks dari halaman mana pun.",
        tips: [
          "Gunakan pencarian wajah bila hanya memiliki foto.",
          "Gunakan pencarian teks untuk nama, jabatan, atau lokasi.",
        ],
        target: topbarSearch,
      });
    }

    const topbarMenu = firstVisible(['[data-tour="topbar-menu"]']);
    if (topbarMenu) {
      steps.push({
        kicker: "Navigasi · Menu",
        title: "Ikon menu di ponsel",
        body:
          "Pada layar kecil, sidebar disembunyikan dan dibuka lewat ikon menu ini.",
        tips: [
          "Ketuk ikon menu untuk melihat seluruh navigasi.",
          "Ketuk area gelap untuk menutup sidebar.",
        ],
        target: topbarMenu,
      });
    }

    const topbarUpload = firstVisible(['[data-tour="topbar-upload"]']);
    if (topbarUpload) {
      steps.push({
        kicker: "Ikon fitur · Unggah",
        title: "Tombol unggah cepat",
        body:
          "Tombol unggah membuka formulir kegiatan baru tanpa meninggalkan konteks halaman.",
        tips: [
          "Lengkapi metadata dan foto sebelum menerbitkan.",
          "Tombol hanya tampil untuk pengelola konten.",
        ],
        target: topbarUpload,
      });
    }

    const roleChip = firstVisible(['[data-tour="topbar-role"]', ".role-chip"]);
    if (roleChip) {
      steps.push({
        kicker: "Ikon fitur · Peran",
        title: "Peran dan hak akses",
        body:
          "Chip peran menunjukkan kewenangan akun Anda. Menu dan aksi di seluruh aplikasi mengikuti peran ini.",
        tips: [
          "Peran menentukan halaman yang dapat dibuka.",
          "Hubungi administrator bila peran tidak sesuai tugas.",
        ],
        target: roleChip,
      });
    }

    const avatar = firstVisible(['[data-tour="topbar-avatar"]', ".topbar-avatar"]);
    if (avatar) {
      steps.push({
        kicker: "Ikon fitur · Profil",
        title: "Foto profil dan pengaturan akun",
        body:
          "Klik foto profil untuk membuka halaman profil, mengganti kata sandi, dan mengelola token API.",
        tips: [
          "Perbarui data profil agar jejak audit akurat.",
          "Cabut token API yang tidak lagi digunakan.",
        ],
        target: avatar,
      });
    }

    /* Isi halaman yang sedang dibuka. */
    const path = (window.location.pathname || "/").replace(/\/+$/, "") || "/";
    const page = document.body.dataset.page || "";
    const detailSteps = detailStepsFor(path);
    const pageSteps = detailSteps.length ? detailSteps : PAGE_STEPS[page] || [];
    let pageStepCount = 0;
    pageSteps.forEach((step) => {
      const target = step.selector ? document.querySelector(step.selector) : null;
      if (step.selector && !isVisible(target)) return;
      steps.push({ ...step, target });
      pageStepCount += 1;
    });

    if (!pageStepCount) {
      const main = firstVisible(["#main-content", ".content"]);
      if (main) {
        steps.push({
          kicker: "Halaman ini",
          title: "Area kerja utama",
          body:
            "Semua konten halaman ditampilkan di area ini. Gunakan filter, kartu, dan tombol aksi yang tersedia untuk menyelesaikan tugas Anda.",
          tips: [
            "Mulai dari filter atau kartu ringkasan di bagian atas.",
            "Gunakan bilah atas untuk pencarian dan aksi cepat.",
          ],
          target: main,
        });
      }
    }

    /* Sidebar dan seluruh ikon navigasi. */
    const sidebar = firstVisible(['[data-tour="sidebar"]', "#sidebar", ".sidebar"]);
    if (sidebar) {
      steps.push({
        kicker: "Navigasi · Sidebar",
        title: "Sidebar dengan ikon fitur",
        body:
          "Setiap menu memakai ikon dan label. Ikon membantu mengenali fitur dengan cepat, sedangkan label memperjelas tujuan halaman.",
        tips: [
          "Menu aktif ditandai dengan latar dan warna aksen.",
          "Pada layar kecil, sidebar dibuka lewat ikon menu.",
        ],
        target: sidebar,
      });
    }

    const seen = new Set();
    const navEls = Array.from(
      document.querySelectorAll(".side-nav .nav-item, .side-bottom .nav-item")
    );
    navEls.forEach((el) => {
      const href = el.getAttribute("href");
      if (!href || seen.has(href)) return;
      seen.add(href);
      const info = PAGE_INFO[href] || {
        title: navLabel(el),
        body: "Halaman ini merupakan bagian dari alur kerja SIDEWA.",
        tips: ["Buka halaman untuk melihat fitur yang tersedia."],
      };
      steps.push({
        kicker: "Peta halaman · Sidebar",
        title: info.title,
        body: info.body,
        tips: info.tips,
        target: el,
        nav: true,
        href,
        linkLabel: `Buka ${info.title}`,
      });
    });

    steps.push({
      kicker: "Selesai",
      title: "Siap bekerja dengan SIDEWA",
      body:
        "Panduan ini menyorot bilah atas, isi halaman, ikon fitur, dan sidebar. Buka kapan saja lewat tombol Asisten SIDEWA di sudut kanan bawah.",
      tips: [
        "Setiap halaman memiliki sorotan fitur yang berbeda.",
        "Gunakan pencarian dan filter untuk menemukan data lebih cepat.",
        "Di ponsel, perluas panel bawah untuk membaca penjelasan lengkap.",
      ],
      target: null,
    });
  }

  buildSteps();

  const total = steps.length;
  let index = 0;
  let lastFocus = null;
  let voiceOn = false;
  let voiceAutoStarted = false;
  let expanded = false;
  let sidebarOpenedByTour = false;
  let raf = 0;

  const isOpen = () => !root.hidden;

  const dotEls = steps.map((step, i) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "tour-dot";
    dot.setAttribute("aria-label", `Langkah ${i + 1}: ${step.title}`);
    dot.addEventListener("click", () => show(i));
    dotsEl.appendChild(dot);
    return dot;
  });

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function stopSpeech() {
    if (!supportsSpeech) return;
    try {
      window.speechSynthesis.cancel();
    } catch {
      /* abaikan */
    }
  }

  const Live = {
    socket: null,
    ready: false,
    connecting: false,
    muted: false,
    failed: false,
    pending: false,
    speaking: false,
    fallbackSpoken: false,
    fallbackTimer: 0,
    audioCtx: null,
    sources: new Set(),
    playbackTime: 0,
  };

  function stopPlayback() {
    Live.sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        /* sudah berhenti */
      }
    });
    Live.sources.clear();
    Live.playbackTime = 0;
  }

  function ensureAudioContext() {
    if (!supportsAudio) return null;
    if (!Live.audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      Live.audioCtx = new Ctx();
    }
    if (Live.audioCtx.state === "suspended") {
      Live.audioCtx.resume().catch(() => {});
    }
    return Live.audioCtx;
  }

  function playPcm(base64, rate) {
    if (!voiceOn || Live.muted || !base64) return;
    const ctx = ensureAudioContext();
    if (!ctx) return;
    try {
      const binary = atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
      const samples = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
      if (!samples.length) return;
      const buffer = ctx.createBuffer(1, samples.length, rate || 24000);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i] / 32768;
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      const now = ctx.currentTime;
      if (Live.playbackTime < now + 0.05) Live.playbackTime = now + 0.05;
      source.start(Live.playbackTime);
      Live.playbackTime += buffer.duration;
      Live.sources.add(source);
      source.onended = () => Live.sources.delete(source);
    } catch {
      /* chunk audio rusak — abaikan */
    }
  }

  function stepLabel() {
    const step = steps[index];
    return step && step.nav ? "Peta halaman SIDEWA" : "Pemandu halaman SIDEWA";
  }

  function updateStatus() {
    if (!statusEl) return;
    let label = stepLabel();
    if (voiceOn) {
      if (Live.ready) label = Live.speaking ? "Gemini 3.8 Live · menjelaskan…" : "Gemini 3.8 Live · siap";
      else if (Live.connecting) label = "Gemini 3.8 Live · menghubungkan…";
      else if (Live.failed) label = "Suara perangkat · Gemini Live tidak tersedia";
      else label = "Suara panduan · Gemini 3.8 Live";
    }
    statusEl.textContent = label;
    const wrap = statusEl.closest(".tour-status");
    if (wrap) {
      wrap.title = label;
      wrap.classList.toggle("is-busy", voiceOn && (Live.connecting || Live.speaking));
      wrap.classList.toggle("is-error", voiceOn && Live.failed);
    }
  }

  function sendLiveContext() {
    if (Live.socket && Live.socket.readyState === WebSocket.OPEN) {
      const step = steps[index];
      Live.socket.send(
        JSON.stringify({ type: "context", index: index + 1, title: step ? step.title : "" })
      );
    }
  }

  function narrationText(step) {
    const tips = (step.tips || []).slice(0, 2).join(" ");
    return [step.title, step.body, tips].filter(Boolean).join(". ").slice(0, 900);
  }

  function speakFallback() {
    if (!voiceOn || !supportsSpeech) return;
    const step = steps[index];
    if (!step) return;
    stopSpeech();
    Live.fallbackSpoken = true;
    Live.speaking = true;
    const text = [step.title, step.body, ...(step.tips || []).slice(0, 2)].join(". ");
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "id-ID";
    utterance.rate = 0.98;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    const indonesian = voices.find((voice) => /^id(-|_)/i.test(voice.lang));
    if (indonesian) utterance.voice = indonesian;
    utterance.onend = () => {
      Live.speaking = false;
      updateStatus();
    };
    window.speechSynthesis.speak(utterance);
    updateStatus();
  }

  function narrateCurrent() {
    if (!voiceOn) return;
    const step = steps[index];
    if (!step) return;
    window.clearTimeout(Live.fallbackTimer);
    Live.fallbackTimer = 0;
    if (Live.ready && Live.socket && Live.socket.readyState === WebSocket.OPEN) {
      if (Live.speaking) {
        try {
          Live.socket.send(JSON.stringify({ type: "cancel" }));
        } catch {
          /* abaikan */
        }
      }
      Live.pending = false;
      Live.fallbackSpoken = false;
      stopSpeech();
      stopPlayback();
      Live.speaking = true;
      updateStatus();
      Live.socket.send(
        JSON.stringify({
          type: "narrate",
          text: narrationText(step),
          index: index + 1,
          title: step.title,
        })
      );
      return;
    }
    Live.pending = true;
    if (Live.connecting) return;
    if (Live.failed) {
      speakFallback();
      return;
    }
    connectLive();
  }

  function handleLivePayload(payload) {
    switch (payload.type) {
      case "ready":
        Live.connecting = false;
        Live.ready = true;
        Live.failed = false;
        window.clearTimeout(Live.fallbackTimer);
        Live.fallbackTimer = 0;
        updateStatus();
        if (Live.pending && voiceOn && !Live.fallbackSpoken) {
          Live.pending = false;
          narrateCurrent();
        }
        break;
      case "audio":
        if (voiceOn) {
          Live.speaking = true;
          playPcm(payload.data, 24000);
          updateStatus();
        }
        break;
      case "output":
        if (voiceOn) {
          Live.speaking = true;
          updateStatus();
        }
        break;
      case "interrupted":
        stopPlayback();
        Live.speaking = false;
        updateStatus();
        break;
      case "turn_complete":
        Live.speaking = false;
        Live.pending = false;
        updateStatus();
        break;
      case "notice":
        if (payload.level && payload.level !== "info") {
          Live.failed = true;
          if (voiceOn) speakFallback();
        }
        updateStatus();
        break;
      case "error":
        Live.speaking = false;
        if (voiceOn) {
          Live.failed = true;
          speakFallback();
        }
        updateStatus();
        break;
      case "upstream_closed":
        Live.speaking = false;
        updateStatus();
        break;
      default:
        break;
    }
  }

  function connectLive() {
    if (!supportsAudio) {
      Live.failed = true;
      speakFallback();
      return;
    }
    if (
      Live.socket &&
      (Live.socket.readyState === WebSocket.OPEN || Live.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    Live.connecting = true;
    Live.failed = false;
    Live.fallbackSpoken = false;
    updateStatus();
    let socket;
    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/panduan/live`);
    } catch {
      Live.connecting = false;
      Live.failed = true;
      speakFallback();
      return;
    }
    Live.socket = socket;

    socket.addEventListener("open", () => {
      sendLiveContext();
    });

    socket.addEventListener("message", (event) => {
      if (Live.socket !== socket) return;
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      handleLivePayload(payload);
    });

    socket.addEventListener("error", () => {
      if (Live.socket === socket) Live.failed = true;
    });

    socket.addEventListener("close", (event) => {
      if (Live.socket !== socket) return;
      Live.socket = null;
      Live.connecting = false;
      Live.ready = false;
      Live.speaking = false;
      stopPlayback();
      if (voiceOn) {
        if (event.code === 4003 || event.code === 4401 || event.code === 4403 || !event.wasClean) {
          Live.failed = true;
          speakFallback();
        }
      }
      updateStatus();
    });

    Live.fallbackTimer = window.setTimeout(() => {
      if (!voiceOn || Live.ready) return;
      Live.failed = true;
      speakFallback();
    }, 9000);
  }

  function disconnectLive() {
    window.clearTimeout(Live.fallbackTimer);
    Live.fallbackTimer = 0;
    Live.pending = false;
    if (!Live.socket) return;
    const socket = Live.socket;
    Live.socket = null;
    Live.ready = false;
    Live.connecting = false;
    try {
      socket.close(1000, "tour closed");
    } catch {
      /* abaikan */
    }
  }

  function setVoice(on) {
    voiceOn = Boolean(on) && supportsVoice;
    if (!voiceBtn) return;
    voiceBtn.classList.toggle("is-on", voiceOn);
    voiceBtn.setAttribute("aria-pressed", voiceOn ? "true" : "false");
    voiceBtn.setAttribute("aria-label", voiceOn ? "Matikan narasi suara" : "Nyalakan narasi suara");
    voiceBtn.title = voiceOn ? "Matikan narasi" : "Narasi suara";
    const use = voiceBtn.querySelector("use");
    if (use) use.setAttribute("href", voiceOn ? "#i-volume" : "#i-volume-off");
    if (voiceOn) {
      ensureAudioContext();
      Live.failed = false;
      Live.fallbackSpoken = false;
      narrateCurrent();
    } else {
      stopSpeech();
      stopPlayback();
      disconnectLive();
      Live.speaking = false;
    }
    updateStatus();
  }

  function renderContent() {
    const step = steps[index];
    if (!step) return;
    if (kickerEl) kickerEl.textContent = step.kicker || "Halaman ini";
    if (counterEl) {
      counterEl.textContent = `${String(index + 1).padStart(2, "0")} / ${String(
        total
      ).padStart(2, "0")}`;
    }
    if (titleEl) titleEl.textContent = step.title;
    if (headTitleEl) {
      headTitleEl.textContent = isSmall() ? step.title : "Asisten SIDEWA";
      headTitleEl.title = step.title;
    }
    if (bodyEl) bodyEl.textContent = step.body || "";
    if (tipsEl) {
      tipsEl.replaceChildren();
      (step.tips || []).forEach((tip) => {
        const li = document.createElement("li");
        li.textContent = tip;
        tipsEl.appendChild(li);
      });
    }
    if (linkEl) {
      if (step.href) {
        linkEl.href = step.href;
        linkEl.hidden = false;
        if (linkLabelEl) linkLabelEl.textContent = step.linkLabel || "Buka halaman";
      } else {
        linkEl.hidden = true;
        linkEl.removeAttribute("href");
      }
    }
    if (progressEl) progressEl.style.width = `${((index + 1) / total) * 100}%`;
    updateStatus();
    dotEls.forEach((dot, i) => {
      dot.classList.toggle("is-active", i === index);
      if (i === index) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
    });
    if (dotsEl && dotEls[index]) {
      const active = dotEls[index];
      const left = active.offsetLeft - (dotsEl.clientWidth - active.offsetWidth) / 2;
      dotsEl.scrollTo({ left: Math.max(0, left), behavior: reducedMotion ? "auto" : "smooth" });
    }
    if (prevBtn) prevBtn.disabled = index === 0;
    if (nextBtn) {
      const last = index === total - 1;
      nextBtn.setAttribute("aria-label", last ? "Selesai dan tutup panduan" : "Langkah berikutnya");
    }
    if (nextLabel) nextLabel.textContent = index === total - 1 ? "Selesai" : "Berikutnya";
    if (liveEl) liveEl.textContent = `Langkah ${index + 1} dari ${total}: ${step.title}`;
  }

  function setExpanded(value) {
    expanded = Boolean(value);
    if (!card) return;
    card.classList.toggle("is-expanded", expanded);
    if (expandBtn) {
      expandBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      expandBtn.setAttribute(
        "aria-label",
        expanded ? "Sembunyikan penjelasan langkah" : "Tampilkan penjelasan langkah"
      );
      expandBtn.title = expanded ? "Sembunyikan penjelasan" : "Tampilkan penjelasan";
      const use = expandBtn.querySelector("use");
      if (use) use.setAttribute("href", expanded ? "#i-chevron-down" : "#i-chevron-up");
    }
    window.setTimeout(() => {
      place();
      const target = resolveTarget();
      if (expanded && target) scrollPageTarget(target);
    }, 30);
  }

  function scrollWithinSidebar(target) {
    const sidebar = target.closest(".sidebar");
    if (!sidebar) return;
    const sr = sidebar.getBoundingClientRect();
    const tr = target.getBoundingClientRect();
    const pad = 14;
    if (tr.top < sr.top + pad || tr.bottom > sr.bottom - pad) {
      const desired = sr.top + (sr.height - tr.height) / 2;
      sidebar.scrollTop += tr.top - desired;
    }
  }

  function scrollableAncestor(target) {
    let el = target.parentElement;
    while (el && el !== document.body && el !== document.documentElement) {
      const style = window.getComputedStyle(el);
      const scrollable = /(auto|scroll|overlay)/.test(style.overflowY);
      if (scrollable && el.scrollHeight > el.clientHeight + 2) return el;
      el = el.parentElement;
    }
    return null;
  }

  function viewportHeight() {
    if (window.visualViewport && window.visualViewport.height) {
      return Math.min(window.innerHeight, window.visualViewport.height);
    }
    return window.innerHeight;
  }

  function scrollPageTarget(target) {
    let rect = target.getBoundingClientRect();
    const scroller = scrollableAncestor(target);
    if (scroller) {
      const sr = scroller.getBoundingClientRect();
      if (rect.top < sr.top + 8 || rect.bottom > sr.bottom - 8) {
        scroller.scrollTop += rect.top - (sr.top + (sr.height - rect.height) / 2);
        rect = target.getBoundingClientRect();
      }
    }
    const topbar = document.querySelector(".topbar");
    const vh = viewportHeight();
    let topLimit = 14;
    if (topbar) {
      const style = window.getComputedStyle(topbar);
      if (style.position === "sticky" || style.position === "fixed") {
        topLimit = topbar.getBoundingClientRect().bottom + 14;
      }
    }
    let bottomLimit = vh - 14;
    if (card) {
      const cr = card.getBoundingClientRect();
      const bottomSheet = isSmall() || (cr.width > window.innerWidth * 0.55 && cr.top > vh * 0.35);
      // Panel bawah (mobile) tidak boleh menutup target yang sedang dijelaskan.
      if (bottomSheet && cr.height && cr.top < vh) {
        bottomLimit = Math.min(bottomLimit, cr.top - 16);
      }
    }
    if (bottomLimit <= topLimit + 64) bottomLimit = vh - 14;

    const behavior = reducedMotion ? "auto" : "smooth";
    if (rect.height >= bottomLimit - topLimit) {
      if (rect.top < topLimit || rect.top > bottomLimit - 48) {
        window.scrollBy({ top: rect.top - topLimit, behavior });
      }
      return;
    }
    if (rect.top >= topLimit && rect.bottom <= bottomLimit) return;
    const desired = topLimit + (bottomLimit - topLimit) / 2;
    window.scrollBy({ top: rect.top + rect.height / 2 - desired, behavior });
  }

  function revealTarget(target) {
    if (!target) return;
    if (target.closest(".sidebar")) {
      const wasOpen = document.body.classList.contains("sidebar-open");
      if (isOffcanvasSidebar() && !wasOpen) {
        sidebarOpenedByTour = true;
        document.body.classList.add("sidebar-open");
      }
      const delay = isOffcanvasSidebar() && !wasOpen && !reducedMotion ? 240 : 0;
      if (delay) {
        window.setTimeout(() => {
          scrollWithinSidebar(target);
          schedulePlace();
        }, delay);
      } else {
        scrollWithinSidebar(target);
        schedulePlace();
      }
      return;
    }
    if (sidebarOpenedByTour) {
      document.body.classList.remove("sidebar-open");
      sidebarOpenedByTour = false;
    }
    scrollPageTarget(target);
  }

  function placeCard(target) {
    if (!card) return;
    if (!target) {
      card.classList.add("is-centered");
      card.style.removeProperty("left");
      card.style.removeProperty("top");
      card.style.removeProperty("right");
      card.style.removeProperty("bottom");
      return;
    }

    card.classList.remove("is-centered");

    if (isSmall()) {
      card.style.removeProperty("left");
      card.style.removeProperty("top");
      card.style.removeProperty("right");
      card.style.removeProperty("bottom");
      return;
    }

    const rect = target.getBoundingClientRect();
    const width = card.offsetWidth || 380;
    const height = card.offsetHeight || 360;
    const gap = 22;
    const margin = 16;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const center = rect.left + rect.width / 2;

    let left;
    if (rect.width > vw * 0.62) {
      left = vw - width - margin;
    } else if (center > vw / 2) {
      left = rect.left - width - gap;
    } else {
      left = rect.right + gap;
    }
    left = clamp(left, margin, vw - width - margin);

    let top = rect.top + rect.height / 2 - height / 2;
    if (rect.width > vw * 0.62) {
      top = vh - height - margin;
    }
    top = clamp(top, margin, vh - height - margin);

    card.style.left = `${Math.round(left)}px`;
    card.style.top = `${Math.round(top)}px`;
    card.style.right = "auto";
    card.style.bottom = "auto";
  }

  function placeSpotlight(target) {
    if (!spotlight) return;
    if (!target) {
      spotlight.hidden = true;
      return;
    }
    const step = steps[index];
    const pad = step && step.nav ? 6 : 9;
    const raw = target.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (raw.bottom < 0 || raw.top > vh || raw.right < 0 || raw.left > vw) {
      spotlight.hidden = true;
      return;
    }
    const left = Math.max(0, Math.min(raw.left, vw - 1));
    const top = Math.max(0, Math.min(raw.top, vh - 1));
    const right = Math.max(left + 1, Math.min(raw.right, vw));
    const bottom = Math.max(top + 1, Math.min(raw.bottom, vh));
    spotlight.hidden = false;
    spotlight.style.left = `${Math.round(left - pad)}px`;
    spotlight.style.top = `${Math.round(top - pad)}px`;
    spotlight.style.width = `${Math.round(right - left + pad * 2)}px`;
    spotlight.style.height = `${Math.round(bottom - top + pad * 2)}px`;
  }

  function resolveTarget() {
    const step = steps[index];
    const target = step && step.target;
    return isVisible(target) ? target : null;
  }

  function place() {
    if (!isOpen()) return;
    const target = resolveTarget();
    root.classList.toggle("is-centered", !target);
    placeCard(target);
    placeSpotlight(target);
  }

  function schedulePlace() {
    if (!isOpen() || raf) return;
    raf = window.requestAnimationFrame(() => {
      raf = 0;
      place();
    });
  }

  function show(target) {
    index = clamp(target, 0, total - 1);
    if (isSmall() && expanded) setExpanded(false);
    renderContent();
    place();
    const el = resolveTarget();
    if (el) {
      revealTarget(el);
      window.setTimeout(place, reducedMotion ? 30 : 380);
      if (isSmall()) window.setTimeout(place, 140);
    } else if (sidebarOpenedByTour) {
      document.body.classList.remove("sidebar-open");
      sidebarOpenedByTour = false;
    }
    if (isOpen()) narrateCurrent();
    if (nextBtn) {
      window.setTimeout(() => {
        if (isOpen()) nextBtn.focus({ preventScroll: true });
      }, 60);
    }
  }

  function goNext() {
    if (index >= total - 1) closeTour();
    else show(index + 1);
  }

  function goPrev() {
    if (index > 0) show(index - 1);
  }

  function openTour(start = 0) {
    if (!isOpen()) {
      lastFocus = document.activeElement;
      root.hidden = false;
      document.body.classList.add("tour-open");
      if (isSmall() && supportsVoice) ensureAudioContext();
    }
    show(start);
    if (isSmall() && supportsVoice && !voiceAutoStarted) {
      voiceAutoStarted = true;
      if (!voiceOn) setVoice(true);
    }
  }

  function closeTour() {
    if (!isOpen()) return;
    stopSpeech();
    stopPlayback();
    disconnectLive();
    if (isSmall()) setExpanded(false);
    root.hidden = true;
    document.body.classList.remove("tour-open");
    if (sidebarOpenedByTour) {
      document.body.classList.remove("sidebar-open");
      sidebarOpenedByTour = false;
    }
    if (spotlight) spotlight.hidden = true;
    if (lastFocus && typeof lastFocus.focus === "function") {
      lastFocus.focus({ preventScroll: true });
    }
  }

  function trapFocus(event) {
    if (!card) return;
    const focusable = Array.from(
      card.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((el) => el.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === card)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  if (fab) fab.addEventListener("click", () => openTour(0));
  root.querySelectorAll("[data-tour-close]").forEach((button) => {
    button.addEventListener("click", closeTour);
  });
  root.querySelectorAll("[data-tour-next]").forEach((button) => {
    button.addEventListener("click", goNext);
  });
  root.querySelectorAll("[data-tour-prev]").forEach((button) => {
    button.addEventListener("click", goPrev);
  });
  if (voiceBtn) {
    if (!supportsVoice) {
      voiceBtn.hidden = true;
    } else {
      voiceBtn.addEventListener("click", () => setVoice(!voiceOn));
    }
  }
  if (expandBtn) {
    expandBtn.addEventListener("click", () => setExpanded(!expanded));
  }
  if (sidebarEl) {
    sidebarEl.addEventListener("transitionend", (event) => {
      if (event.target === sidebarEl && event.propertyName === "transform") schedulePlace();
    });
  }
  if (blocker) {
    blocker.addEventListener("click", () => {
      /* Klik di luar kartu tidak menutup otomatis agar tur tidak terhenti. */
    });
  }

  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    const key = event.key;
    if (key === "Escape") {
      event.preventDefault();
      closeTour();
      return;
    }
    if (key === "Tab") {
      trapFocus(event);
      return;
    }
    if (key === "ArrowRight" || key === "ArrowDown" || key === "PageDown" || key === " ") {
      event.preventDefault();
      goNext();
    } else if (key === "ArrowLeft" || key === "ArrowUp" || key === "PageUp") {
      event.preventDefault();
      goPrev();
    } else if (key === "Home") {
      event.preventDefault();
      show(0);
    } else if (key === "End") {
      event.preventDefault();
      show(total - 1);
    }
  });

  window.addEventListener("resize", schedulePlace);
  window.addEventListener("scroll", schedulePlace, { passive: true });
  window.addEventListener("orientationchange", schedulePlace);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", schedulePlace);
    window.visualViewport.addEventListener("scroll", schedulePlace);
  }
  const smallScreen = window.matchMedia("(max-width: 760px)");
  if (smallScreen.addEventListener) {
    smallScreen.addEventListener("change", () => {
      if (!isSmall()) setExpanded(false);
      schedulePlace();
    });
  }

  if (supportsSpeech) {
    window.speechSynthesis.addEventListener?.("voiceschanged", () => {
      if (voiceOn && Live.failed) speakFallback();
    });
  }

  window.SIDEWA = Object.assign(window.SIDEWA || {}, {
    openHumasAssistant: openTour,
    closeHumasAssistant: closeTour,
    goToHumasAssistantStep: show,
  });
})();
