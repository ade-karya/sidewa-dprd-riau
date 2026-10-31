(() => {
  "use strict";

  const toast = (text) => {
    if (window.SIDEWA && typeof window.SIDEWA.toast === "function") {
      window.SIDEWA.toast(text);
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return "segera";
    if (seconds < 60) return `± ${seconds} detik`;
    const minutes = Math.ceil(seconds / 60);
    if (minutes < 60) return `± ${minutes} menit`;
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest ? `± ${hours} jam ${rest} menit` : `± ${hours} jam`;
  };

  /* ── Prefill target & skor dari skill ─────────────────────────────────── */
  const startForm = document.querySelector("[data-ps-start]");
  if (startForm) {
    const target = startForm.querySelector('input[name="target_count"]');
    const score = startForm.querySelector('input[name="min_score"]');
    const notes = startForm.querySelector('textarea[name="notes"]');
    const skillInputs = startForm.querySelectorAll('input[name="skill_key"]');
    const cards = startForm.querySelectorAll("[data-ps-skill]");
    let userTouchedScore = false;

    const applySkill = (card) => {
      if (!card) return;
      const cardTarget = card.dataset.target;
      const cardScore = card.dataset.score;
      if (target && cardTarget !== undefined) target.value = cardTarget;
      if (score && cardScore !== undefined && !userTouchedScore) {
        score.value = cardScore;
      }
      if (notes) {
        const label = card.querySelector("strong");
        notes.placeholder = label
          ? `Preferensi tambahan untuk skill “${label.textContent.trim()}”…`
          : "Tulis preferensi tambahan untuk sesi ini…";
      }
    };

    cards.forEach((card) => {
      const input = card.querySelector('input[name="skill_key"]');
      if (!input) return;
      input.addEventListener("change", () => {
        cards.forEach((item) => item.classList.toggle("selected", item === card));
        applySkill(card);
      });
      if (input.checked) {
        card.classList.add("selected");
        applySkill(card);
      }
    });

    if (score) {
      score.addEventListener("input", () => {
        userTouchedScore = true;
      });
    }

    /* ── Estimasi unggahan ──────────────────────────────────────────────── */
    const fileInput = startForm.querySelector("[data-ps-photos]");
    const estimate = document.querySelector("[data-ps-estimate-text]");
    const summary = document.querySelector("[data-ps-file-summary]");
    const rpm = Math.max(1, Number(startForm.dataset.rpm || 15));
    const rpdRemaining = Math.max(0, Number(startForm.dataset.rpdRemaining || 0));
    const max = Number(fileInput?.dataset.max || 24);
    const maxMb = Math.max(1, Number(startForm.dataset.maxMb || 15));
    const maxBytes = maxMb * 1024 * 1024;

    const updateEstimate = () => {
      const files = Array.from(fileInput?.files || []);
      if (!files.length) {
        if (estimate) estimate.textContent = "Pilih foto untuk melihat estimasi waktu dan kuota.";
        if (summary) summary.hidden = true;
        return;
      }
      const totalBytes = files.reduce((sum, file) => sum + (file.size || 0), 0);
      const sizeText =
        totalBytes > 1024 * 1024
          ? `${(totalBytes / 1024 / 1024).toFixed(1)} MB`
          : `${Math.max(1, Math.round(totalBytes / 1024))} KB`;
      const oversized = files.filter((file) => file.size > maxBytes);
      const estimateSeconds = Math.ceil(Math.min(files.length, rpdRemaining || files.length) / rpm * 60);
      if (estimate) {
        const quotaNote = rpdRemaining <= 0
          ? "Kuota harian habis; sesi akan dijeda dan dapat dilanjutkan."
          : files.length > rpdRemaining
            ? `Kuota tersisa ${rpdRemaining} foto; sisanya otomatis dijeda.`
            : `${files.length} permintaan AI dari ${rpdRemaining} slot tersisa.`;
        estimate.textContent = `${files.length} foto · ${sizeText} · ${formatDuration(estimateSeconds)} pada ${rpm} RPM. ${quotaNote}`;
      }
      if (summary) {
        summary.hidden = false;
        summary.textContent = oversized.length
          ? `${files.length} foto dipilih · ${oversized.length} melebihi ${maxMb} MB/foto`
          : `${files.length} foto dipilih · ${sizeText}`;
      }
      if (files.length > max) {
        toast(`Maksimal ${max} foto per sesi. Hapus ${files.length - max} foto sebelum melanjutkan.`);
      } else if (oversized.length) {
        toast(`${oversized.length} foto melebihi batas ${maxMb} MB per berkas.`);
      }
    };

    fileInput?.addEventListener("change", updateEstimate);
    updateEstimate();

    startForm.addEventListener("submit", (event) => {
      const files = Array.from(fileInput?.files || []);
      if (files.length > max) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast(`Maksimal ${max} foto per sesi.`);
      } else if (files.some((file) => file.size > maxBytes)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast(`Setiap foto maksimal ${maxMb} MB.`);
      }
    });
  }

  /* ── Polling status sesi ──────────────────────────────────────────────── */
  const runRoot = document.querySelector("[data-ps-run]");
  if (runRoot) {
    const statusUrl = runRoot.dataset.statusUrl;
    const terminal = new Set(["done", "failed", "cancelled"]);
    const badge = runRoot.querySelector("[data-ps-status-badge]");
    const label = runRoot.querySelector("[data-ps-status-label]");
    const progress = runRoot.querySelector("[data-ps-progress]");
    const progressText = runRoot.querySelector("[data-ps-progress-text]");
    const liveTitle = runRoot.querySelector("[data-ps-live-title]");
    const waitText = runRoot.querySelector("[data-ps-wait-text]");
    let attempts = 0;
    let timer = null;

    const stat = (name, value) => {
      const el = runRoot.querySelector(`[data-ps-stat="${name}"]`);
      if (el) el.textContent = value;
    };

    const schedule = (seconds) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(poll, Math.max(2500, seconds * 1000));
    };

    const apply = (data) => {
      if (progress) progress.style.width = `${data.progress || 0}%`;
      if (progressText) progressText.textContent = `${data.processed}/${data.total}`;
      stat("selected", data.selected);
      stat("backup", data.backup);
      stat("rejected", data.rejected);
      stat("quota", data.quota_used);
      if (label && data.status_label) label.textContent = data.status_label;
      if (badge) {
        const tone = data.status === "done" ? "green" : data.status === "paused" ? "blue" : data.status === "failed" ? "red" : "gold";
        badge.className = `badge badge-${tone}`;
      }
      if (waitText && data.wait_seconds > 0) {
        if (liveTitle) liveTitle.textContent = "Menunggu kuota API";
        waitText.textContent = `Permintaan berikutnya dalam ${data.wait_seconds} detik.`;
      } else if (waitText) {
        waitText.textContent = "Foto sedang dikirim ke Gemini.";
      }
      if (data.terminal) {
        window.clearTimeout(timer);
        window.location.reload();
      }
    };

    const poll = async () => {
      attempts += 1;
      try {
        const response = await fetch(statusUrl, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("status");
        const data = await response.json();
        apply(data);
        if (!data.terminal && attempts < 900) {
          schedule(data.wait_seconds > 0 ? Math.min(data.wait_seconds + 1, 30) : 4);
        }
      } catch {
        if (attempts < 20) schedule(6);
      }
    };

    if (statusUrl && !terminal.has(runRoot.dataset.status)) schedule(3);
  }

  /* ── Filter hasil ─────────────────────────────────────────────────────── */
  const filterTabs = document.querySelectorAll("[data-ps-filter]");
  if (filterTabs.length) {
    filterTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const filter = tab.dataset.psFilter;
        filterTabs.forEach((item) => item.classList.toggle("active", item === tab));
        document.querySelectorAll("[data-ps-card]").forEach((card) => {
          card.hidden = filter !== "all" && card.dataset.verdict !== filter;
        });
      });
    });
  }

  /* ── Simpan verdict otomatis ──────────────────────────────────────────── */
  const verdictForm = document.querySelector("[data-ps-verdict-form]");
  if (verdictForm) {
    const labels = {
      selected: "Dipilih",
      backup: "Cadangan",
      rejected: "Ditolak",
      failed: "Gagal",
      pending: "Menunggu",
    };
    const tones = { selected: "green", backup: "gold", rejected: "red", failed: "red", pending: "gray" };
    let saveTimer = null;

    const updateCounts = (data) => {
      const map = { selected: data.selected, backup: data.backup, rejected: data.rejected };
      filterTabs.forEach((tab) => {
        const key = tab.dataset.psFilter;
        const target = tab.querySelector("span");
        if (target && key in map) target.textContent = map[key];
      });
      const allTab = document.querySelector('[data-ps-filter="all"] span');
      if (allTab) {
        allTab.textContent = Number(data.selected) + Number(data.backup) + Number(data.rejected);
      }
      document.querySelectorAll("[data-ps-selected-count]").forEach((el) => {
        el.textContent = data.selected;
      });
      const mobileCount = document.querySelector("[data-ps-mobile-count]");
      if (mobileCount) mobileCount.textContent = data.selected;
    };

    const save = async () => {
      const button = verdictForm.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      try {
        const response = await fetch(verdictForm.action, {
          method: "POST",
          body: new FormData(verdictForm),
          headers: { "x-requested-with": "fetch", Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("save");
        const data = await response.json();
        updateCounts(data);
        toast(
          data.learned
            ? "Pilihan disimpan. Skill diperbarui otomatis dari preferensi Anda."
            : "Pilihan disimpan."
        );
      } catch {
        toast("Gagal menyimpan otomatis. Gunakan tombol Simpan perubahan.");
      } finally {
        if (button) button.disabled = false;
      }
    };

    verdictForm.querySelectorAll('input[type="radio"][name^="verdict_"]').forEach((input) => {
      input.addEventListener("change", () => {
        const card = input.closest("[data-ps-card]");
        if (!card) return;
        const verdict = input.value;
        card.dataset.verdict = verdict;
        card.querySelectorAll(".ps-verdict-option").forEach((option) => {
          option.classList.toggle("selected", option.contains(input));
        });
        const badge = card.querySelector("[data-ps-verdict-badge]");
        if (badge) {
          badge.className = `badge badge-${tones[verdict] || "gray"}`;
          badge.textContent = labels[verdict] || verdict;
        }
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(save, 350);
      });
    });
  }

  /* ── Kirim & unduh foto asli (bukan tautan, teks, atau ZIP) ──────────── */
  const selectedCards = () =>
    Array.from(document.querySelectorAll("[data-ps-card]")).filter(
      (card) => card.dataset.verdict === "selected"
    );

  const photoButton = (card) => card?.querySelector("[data-ps-share-one]");
  const photoUrlFor = (card) => photoButton(card)?.dataset.psPhotoUrl || "";

  // Simpan permintaan yang sedang berjalan agar sentuhan pertama di ponsel
  // sudah mulai mengunduh foto sebelum lembar berbagi iOS/Android dibuka.
  const photoRequests = new Map();

  const extensionFor = (type, name = "") => {
    const byType = { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp" };
    if (byType[type]) return byType[type];
    const match = String(name).match(/\.(jpe?g|png|webp)$/i);
    if (!match) return ".jpg";
    return `.${match[1].toLowerCase().replace("jpeg", "jpg")}`;
  };

  const filenameFor = (card, type) => {
    const raw = (photoButton(card)?.dataset.psPhotoName || "").trim() || "foto";
    const stem = raw
      .replace(/\.[a-z0-9]{2,5}$/i, "")
      .replace(/[\\/:*?"<>|\r\n]+/g, "-")
      .trim()
      .slice(0, 90);
    return `${stem || "foto"}${extensionFor(type, raw)}`;
  };

  // Ambil berkas foto asli dari server dan pastikan isinya benar-benar gambar.
  const fetchPhoto = async (card) => {
    const url = photoUrlFor(card);
    if (!url) throw new Error("URL foto tidak tersedia");
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "image/*" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const type = (blob.type || "").toLowerCase();
    if (!type.startsWith("image/") || blob.size === 0) {
      throw new Error("Berkas yang diterima bukan foto");
    }
    return { blob, type, filename: filenameFor(card, type) };
  };

  const requestPhoto = (card) => {
    const url = photoUrlFor(card);
    if (!url) return Promise.reject(new Error("URL foto tidak tersedia"));
    const pending = photoRequests.get(url);
    if (pending) return pending;
    const request = fetchPhoto(card).catch((error) => {
      photoRequests.delete(url);
      throw error;
    });
    photoRequests.set(url, request);
    // Bersihkan prefetch yang tidak jadi dipakai agar memori ponsel aman.
    window.setTimeout(() => {
      if (photoRequests.get(url) === request) photoRequests.delete(url);
    }, 20000);
    return request;
  };

  const forgetPhoto = (card) => {
    const url = photoUrlFor(card);
    if (url) photoRequests.delete(url);
  };

  const prefetchPhoto = (card) => {
    requestPhoto(card).catch(() => {});
  };

  const isIos = () =>
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

  const canShareFiles = (files) => {
    if (typeof navigator.share !== "function") return false;
    if (typeof navigator.canShare !== "function") return true;
    try {
      return !!navigator.canShare({ files });
    } catch (error) {
      return false;
    }
  };

  const savePhoto = (photo) => {
    const href = URL.createObjectURL(photo.blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = photo.filename;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Jangan cabut terlalu cepat: unduhan foto besar di ponsel masih berjalan.
    window.setTimeout(() => URL.revokeObjectURL(href), 60000);
  };

  let actionBusy = false;

  const withBusy = (button, task) => {
    if (!button || actionBusy) return;
    actionBusy = true;
    button.disabled = true;
    let pending;
    try {
      // Jalankan langsung di dalam gesture klik agar lembar berbagi iOS/Android
      // tetap dianggap dipicu pengguna.
      pending = task();
    } catch (error) {
      pending = Promise.reject(error);
    }
    Promise.resolve(pending)
      .catch(() => toast("Foto tidak dapat disiapkan. Muat ulang halaman lalu coba lagi."))
      .finally(() => {
        actionBusy = false;
        button.disabled = false;
      });
  };

  const bindPhotoPrefetch = (button, prefetch) => {
    if (!button) return;
    const arm = () => prefetch();
    button.addEventListener("pointerdown", arm, { passive: true });
    button.addEventListener("touchstart", arm, { passive: true });
  };

  // Kirim satu foto lewat lembar berbagi perangkat; fallback mengunduh foto asli.
  document.querySelectorAll("[data-ps-share-one]").forEach((button) => {
    bindPhotoPrefetch(button, () => prefetchPhoto(button.closest("[data-ps-card]")));
    button.addEventListener("click", () => {
      withBusy(button, async () => {
        const card = button.closest("[data-ps-card]");
        try {
          const photo = await requestPhoto(card);
          const file = new File([photo.blob], photo.filename, { type: photo.type });
          if (canShareFiles([file])) {
            try {
              await navigator.share({ files: [file] });
              return;
            } catch (error) {
              if (error?.name === "AbortError") return;
            }
          }
          savePhoto(photo);
          toast("Peramban belum bisa mengirim berkas langsung. Foto asli diunduh agar dapat dilampirkan manual.");
        } finally {
          forgetPhoto(card);
        }
      });
    });
  });

  // Unduh satu foto asli langsung dari kartu (ramah Android dan iPhone).
  document.querySelectorAll("[data-ps-download-one]").forEach((button) => {
    bindPhotoPrefetch(button, () => prefetchPhoto(button.closest("[data-ps-card]")));
    button.addEventListener("click", () => {
      withBusy(button, async () => {
        const card = button.closest("[data-ps-card]");
        try {
          savePhoto(await requestPhoto(card));
          toast("Foto asli diunduh.");
        } finally {
          forgetPhoto(card);
        }
      });
    });
  });

  // Kirim semua foto terpilih sekaligus sebagai berkas gambar.
  document.querySelectorAll("[data-ps-share-whatsapp]").forEach((button) => {
    button.addEventListener("click", () => {
      withBusy(button, async () => {
        const cards = selectedCards();
        if (!cards.length) {
          toast("Belum ada foto berstatus Dipilih untuk dikirim.");
          return;
        }
        const photos = [];
        let failed = 0;
        for (const card of cards) {
          try {
            photos.push(await requestPhoto(card));
          } catch (error) {
            console.warn("Gagal menyiapkan foto:", error);
            failed += 1;
          } finally {
            forgetPhoto(card);
          }
        }
        if (!photos.length) {
          toast("Foto terpilih tidak dapat disiapkan. Coba muat ulang halaman.");
          return;
        }
        const files = photos.map(
          (photo) => new File([photo.blob], photo.filename, { type: photo.type })
        );
        if (canShareFiles(files)) {
          try {
            await navigator.share({ files });
            return;
          } catch (error) {
            if (error?.name === "AbortError") return;
          }
        }
        // Peramban tanpa berbagi berkas: unduh foto aslinya satu per satu.
        for (const photo of photos) {
          savePhoto(photo);
          await new Promise((resolve) => setTimeout(resolve, 180));
        }
        const hint = isIos()
          ? "Jika iPhone hanya menyimpan satu foto, ketuk Unduh pada tiap foto."
          : "Jika peramban meminta izin unduhan ganda, pilih Izinkan.";
        toast(
          failed
            ? `${photos.length} foto asli diunduh, ${failed} gagal. ${hint}`
            : `Foto tidak bisa dikirim langsung; ${photos.length} foto asli diunduh. ${hint}`
        );
      });
    });
  });

  // Unduh semua foto terpilih sebagai berkas gambar asli, bukan ZIP.
  document.querySelectorAll("[data-ps-download-all]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      withBusy(button, async () => {
        const cards = selectedCards();
        if (!cards.length) {
          toast("Belum ada foto berstatus Dipilih untuk diunduh.");
          return;
        }
        let saved = 0;
        let failed = 0;
        for (const card of cards) {
          try {
            savePhoto(await requestPhoto(card));
            saved += 1;
          } catch (error) {
            console.warn("Gagal mengunduh foto:", error);
            failed += 1;
          } finally {
            forgetPhoto(card);
          }
          await new Promise((resolve) => setTimeout(resolve, 180));
        }
        const hint = isIos()
          ? "Jika iPhone hanya menyimpan satu foto, ketuk Unduh pada tiap foto."
          : "Jika peramban meminta izin unduhan ganda, pilih Izinkan.";
        if (!saved) {
          toast("Foto terpilih tidak dapat diunduh. Coba muat ulang halaman.");
        } else if (failed) {
          toast(`${saved} foto asli diunduh, ${failed} gagal. ${hint}`);
        } else {
          toast(`${saved} foto asli diunduh. ${hint}`);
        }
      });
    });
  });

  // Tampilkan aksi kirim/unduh hanya pada kartu berstatus Dipilih dan
  // sinkronkan bilah aksi bawah khusus ponsel.
  const syncSelectedActions = () => {
    const total = selectedCards().length;
    document.querySelectorAll("[data-ps-card]").forEach((card) => {
      const actions = card.querySelector("[data-ps-card-actions]");
      if (actions) actions.hidden = card.dataset.verdict !== "selected";
    });
    document.querySelectorAll(".ps-global-action").forEach((button) => {
      button.hidden = total === 0;
    });
    const bar = document.querySelector("[data-ps-mobile-actions]");
    if (bar) {
      bar.hidden = total === 0;
      const count = bar.querySelector("[data-ps-mobile-count]");
      if (count) count.textContent = total;
    }
  };

  document.querySelectorAll("[data-ps-card] input[type='radio'][name^='verdict_']").forEach((input) => {
    input.addEventListener("change", syncSelectedActions);
  });
  syncSelectedActions();
})();
