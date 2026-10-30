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
  const statusEl = root.querySelector("[data-tour-status]");

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const supportsVoice = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const isSmall = () => window.matchMedia("(max-width: 760px)").matches;

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
        selector: '[data-tour="humas-shortcuts"]',
        kicker: "Halaman ini · Pintasan",
        title: "Pintasan ruang kerja",
        body:
          "Setiap ubin membuka tugas yang paling sering dipakai tim Humas, dari unggah dokumentasi sampai seleksi foto.",
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
  };

  const steps = [];

  function navLabel(el) {
    const label = el.querySelector(".nav-label");
    return (label ? label.textContent : el.textContent || "").trim();
  }

  function buildSteps() {
    steps.push({
      kicker: "Asisten SIDEWA",
      title: "Mengenal SIDEWA",
      body:
        "Saya akan memandu Anda mengenali halaman-halaman SIDEWA dan cara memakainya. Setiap langkah akan menyorot bagian layar yang sedang dijelaskan.",
      tips: [
        "Gunakan tombol Berikutnya atau tombol panah untuk berpindah langkah.",
        "Tekan Esc kapan saja untuk menutup panduan.",
        "Nyalakan narasi suara bila ingin penjelasan dibacakan.",
      ],
      target: null,
    });

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
        kicker: "Peta halaman",
        title: info.title,
        body: info.body,
        tips: info.tips,
        target: el,
        nav: true,
        href,
        linkLabel: `Buka ${info.title}`,
      });
    });

    const page = document.body.dataset.page || "";
    const pageSteps = PAGE_STEPS[page] || [];
    pageSteps.forEach((step) => {
      const target = step.selector ? document.querySelector(step.selector) : null;
      if (step.selector && !target) return;
      steps.push({ ...step, target });
    });

    steps.push({
      kicker: "Selesai",
      title: "Siap bekerja dengan SIDEWA",
      body:
        "Panduan singkat ini bisa dibuka kapan saja lewat tombol Asisten SIDEWA di sudut kanan bawah.",
      tips: [
        "Mulai dari Ruang Kerja untuk tugas harian Humas.",
        "Gunakan pencarian dan filter untuk menemukan data lebih cepat.",
        "Buka panduan Kenali SIDEWA di halaman login untuk presentasi lengkap.",
      ],
      target: null,
    });
  }

  buildSteps();

  const total = steps.length;
  let index = 0;
  let lastFocus = null;
  let voiceOn = false;
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

  function stopVoice() {
    if (!supportsVoice) return;
    try {
      window.speechSynthesis.cancel();
    } catch {
      /* abaikan */
    }
  }

  function speakStep() {
    if (!voiceOn || !supportsVoice) return;
    const step = steps[index];
    if (!step) return;
    stopVoice();
    const text = [step.title, step.body, ...(step.tips || [])].join(". ");
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "id-ID";
    utterance.rate = 0.98;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    const indonesian = voices.find((voice) => /^id(-|_)/i.test(voice.lang));
    if (indonesian) utterance.voice = indonesian;
    window.speechSynthesis.speak(utterance);
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
    if (voiceOn) speakStep();
    else stopVoice();
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
    if (statusEl) {
      statusEl.textContent = step.nav ? "Peta halaman SIDEWA" : "Pemandu halaman Humas";
    }
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
    const rect = target.getBoundingClientRect();
    spotlight.hidden = false;
    spotlight.style.left = `${Math.round(rect.left - pad)}px`;
    spotlight.style.top = `${Math.round(rect.top - pad)}px`;
    spotlight.style.width = `${Math.round(rect.width + pad * 2)}px`;
    spotlight.style.height = `${Math.round(rect.height + pad * 2)}px`;
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
    renderContent();
    place();
    const step = steps[index];
    const el = resolveTarget();
    if (el && step && !step.nav) {
      const behavior = reducedMotion ? "auto" : "smooth";
      if (isSmall()) {
        const top = el.getBoundingClientRect().top + window.scrollY - 96;
        window.scrollTo({ top: Math.max(0, top), behavior });
      } else {
        el.scrollIntoView({ block: "center", inline: "nearest", behavior });
      }
      window.setTimeout(place, reducedMotion ? 20 : 360);
    }
    speakStep();
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
    }
    show(start);
  }

  function closeTour() {
    if (!isOpen()) return;
    stopVoice();
    root.hidden = true;
    document.body.classList.remove("tour-open");
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

  if (supportsVoice) {
    window.speechSynthesis.addEventListener?.("voiceschanged", () => {
      if (voiceOn) speakStep();
    });
  }

  window.SIDEWA = Object.assign(window.SIDEWA || {}, {
    openHumasAssistant: openTour,
    closeHumasAssistant: closeTour,
    goToHumasAssistantStep: show,
  });
})();
