(() => {
  "use strict";

  const body = document.body;
  const on = (selector, event, handler, root = document) => {
    root.querySelectorAll(selector).forEach((el) => el.addEventListener(event, handler));
  };

  /* Sidebar */
  on("[data-sidebar-open]", "click", () => body.classList.add("sidebar-open"));
  on("[data-sidebar-close], .sidebar-overlay", "click", () => body.classList.remove("sidebar-open"));
  document.querySelectorAll(".sidebar .nav-item").forEach((link) =>
    link.addEventListener("click", () => body.classList.remove("sidebar-open"))
  );

  /* Ringkasan unggah Drive (dibuat sebelum flash agar ikut ditutup otomatis) */
  const flashStack = () => {
    let stack = document.querySelector(".content > .flash-stack");
    if (stack) return stack;
    const main = document.getElementById("main-content");
    if (!main) return null;
    stack = document.createElement("div");
    stack.className = "flash-stack";
    stack.setAttribute("aria-live", "polite");
    main.prepend(stack);
    return stack;
  };
  const addFlash = (category, text) => {
    const stack = flashStack();
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `flash flash-${category}`;
    const iconWrap = document.createElement("span");
    iconWrap.className = "flash-icon";
    iconWrap.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#i-${category === "success" ? "check" : "alert"}"></use></svg>`;
    const message = document.createElement("span");
    message.className = "flash-text";
    message.textContent = text;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "flash-close";
    close.setAttribute("data-dismiss", "");
    close.setAttribute("aria-label", "Tutup");
    close.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg>';
    el.append(iconWrap, message, close);
    stack.append(el);
  };
  try {
    const rawSummary = sessionStorage.getItem("sidewa:drive-upload");
    if (rawSummary) {
      sessionStorage.removeItem("sidewa:drive-upload");
      const summary = JSON.parse(rawSummary) || {};
      const stopped = summary.cancelled === true;
      if (summary.saved) {
        const doneText = stopped
          ? `${summary.saved} berkas tersimpan sebelum unggahan dibatalkan.`
          : `${summary.saved} berkas berhasil diunggah.`;
        addFlash("success", doneText);
        toast(doneText);
      }
      const summaryErrors = Array.isArray(summary.errors) ? summary.errors : [];
      if (summaryErrors.length) {
        const shown = summaryErrors.slice(0, 3).join(" · ");
        addFlash(
          "warning",
          summaryErrors.length > 3 ? `${shown} · +${summaryErrors.length - 3} masalah lain.` : shown
        );
        toast(summaryErrors[0]);
      }
    }
  } catch {
    /* abaikan ringkasan rusak */
  }

  /* Flash */
  const dismiss = (el) => {
    el.style.transition = "opacity .2s, transform .2s";
    el.style.opacity = "0";
    el.style.transform = "translateY(-4px)";
    setTimeout(() => el.remove(), 210);
  };
  on("[data-dismiss]", "click", (event) => dismiss(event.currentTarget.closest(".flash")));
  document.querySelectorAll(".flash").forEach((flash) => {
    const timer = flash.classList.contains("flash-danger") ? 10000 : 6500;
    setTimeout(() => flash.isConnected && dismiss(flash), timer);
  });

  /* Password visibility */
  on("[data-toggle-password]", "click", (event) => {
    event.preventDefault();
    const button = event.currentTarget;
    const input = button.closest(".password-wrap")?.querySelector("input");
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.setAttribute("aria-label", showing ? "Tampilkan kata sandi" : "Sembunyikan kata sandi");
    button.classList.toggle("active", !showing);
  });

  /* Demo accounts */
  on("[data-demo-user]", "click", (event) => {
    const button = event.currentTarget;
    const username = document.querySelector('input[name="username"]');
    const password = document.querySelector('input[name="password"]');
    if (!username || !password) return;
    username.value = button.dataset.demoUser || "";
    password.value = button.dataset.demoPass || "";
    username.dispatchEvent(new Event("input", { bubbles: true }));
    password.dispatchEvent(new Event("input", { bubbles: true }));
    password.focus();
    toast("Akun demo terisi. Tekan Masuk untuk melanjutkan.");
  });

  /* Confirm */
  on("form[data-confirm]", "submit", (event) => {
    const message = event.currentTarget.dataset.confirm || "Lanjutkan tindakan ini?";
    if (!window.confirm(message)) event.preventDefault();
  });

  /* Copy */
  on("[data-copy]", "click", async (event) => {
    const value = event.currentTarget.dataset.copy || "";
    try {
      await navigator.clipboard.writeText(value);
      toast("Disalin ke papan klip.");
    } catch {
      toast("Gagal menyalin. Salin secara manual.");
    }
  });

  /* Print */
  on("[data-print]", "click", () => window.print());

  /* Toast */
  function toast(text) {
    const root = document.getElementById("toast-root");
    if (!root) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    root.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 220);
    }, 3200);
  }

  /* Upload preview */
  on('input[type="file"][data-preview]', "change", (event) => {
    const input = event.currentTarget;
    const target = document.querySelector(input.dataset.preview);
    if (!target) return;
    target.innerHTML = "";
    const files = Array.from(input.files || []);
    const max = Number(input.dataset.max || 12);
    files.slice(0, max).forEach((file) => {
      if (!file.type.startsWith("image/")) return;
      const item = document.createElement("div");
      item.className = "upload-preview";
      const img = document.createElement("img");
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      img.onload = () => URL.revokeObjectURL(img.src);
      const label = document.createElement("span");
      label.textContent = file.name;
      item.append(img, label);
      target.appendChild(item);
    });
    if (files.length > max) toast(`Maksimal ${max} foto. Hanya ${max} pertama yang akan diunggah.`);
  });

  /* Drag state */
  on(".upload-zone input[type=file]", "dragenter", (event) => {
    event.currentTarget.closest(".upload-zone")?.classList.add("dragover");
  });
  on(".upload-zone input[type=file]", "dragleave", (event) => {
    event.currentTarget.closest(".upload-zone")?.classList.remove("dragover");
  });
  on(".upload-zone input[type=file]", "drop", (event) => {
    event.currentTarget.closest(".upload-zone")?.classList.remove("dragover");
  });
  on(".upload-zone input[type=file]", "change", (event) => {
    const input = event.currentTarget;
    const hint = input.closest(".upload-zone")?.querySelector("[data-upload-hint]");
    if (!hint) return;
    if (!hint.dataset.default) hint.dataset.default = hint.textContent;
    const files = Array.from(input.files || []);
    if (!files.length) {
      hint.textContent = hint.dataset.default;
      return;
    }
    const names = files.slice(0, 3).map((file) => file.name).join(", ");
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    hint.textContent = `${files.length} berkas dipilih (${(totalSize / (1024 * 1024)).toFixed(1)} MB): ${names}${files.length > 3 ? ", …" : ""}`;
  });

  /* Drive: kirim satu berkas per permintaan agar tidak kena 413 dari Cloudflare */
  const driveUpload = document.querySelector("form[data-drive-upload]");
  if (driveUpload) {
    const fileInput = driveUpload.querySelector('input[type="file"]');
    const submitBtn = driveUpload.querySelector('button[type="submit"]');
    const hint = driveUpload.querySelector("[data-upload-hint]");
    const progress = driveUpload.querySelector("[data-upload-progress]");
    const bar = driveUpload.querySelector("[data-upload-bar]");
    const track = driveUpload.querySelector("[data-upload-track]");
    const statusEl = driveUpload.querySelector("[data-upload-status]");
    const percentEl = driveUpload.querySelector("[data-upload-percent]");
    const speedEl = driveUpload.querySelector("[data-upload-speed]");
    const cancelBtn = driveUpload.querySelector("[data-upload-cancel]");
    const maxBytes = Number(driveUpload.dataset.maxBytes || 0);
    const maxMb = Number(driveUpload.dataset.maxMb || 0) || Math.round(maxBytes / (1024 * 1024));
    const defaultHint = hint ? hint.textContent.trim() : "";

    let cancelRequested = false;
    let activeXhr = null;
    let lastPaint = 0;

    const humanBytes = (bytes) => {
      if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
      if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
      if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
      return `${Math.max(0, Math.round(bytes))} B`;
    };
    const setHint = (text) => {
      if (hint) hint.textContent = text;
    };
    const setStatus = (text) => {
      if (statusEl) statusEl.textContent = text;
    };
    const setProgress = (loaded, total, force = false) => {
      const now = performance.now();
      if (!force && now - lastPaint < 100) return;
      lastPaint = now;
      const ratio = total > 0 ? Math.max(0, Math.min(1, loaded / total)) : 0;
      const percent = Math.round(ratio * 100);
      if (bar) bar.style.width = `${percent}%`;
      if (track) track.setAttribute("aria-valuenow", String(percent));
      if (percentEl) percentEl.textContent = `${percent}%`;
    };

    const uploadOne = (file, onProgress) =>
      new Promise((resolve, reject) => {
        const data = new FormData();
        driveUpload.querySelectorAll('input[type="hidden"]').forEach((field) => {
          if (field.name) data.append(field.name, field.value);
        });
        data.append("files", file, file.name);

        const xhr = new XMLHttpRequest();
        activeXhr = xhr;
        xhr.open("POST", driveUpload.action || "/drive/unggah");
        xhr.setRequestHeader("X-Drive-Ajax", "1");
        xhr.setRequestHeader("Accept", "application/json");
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) onProgress(event.loaded);
        });
        xhr.addEventListener("load", () => {
          activeXhr = null;
          let payload = null;
          try {
            payload = JSON.parse(xhr.responseText);
          } catch {
            payload = null;
          }
          if (xhr.status === 413) {
            reject(new Error("berkas terlalu besar untuk dikirim (413)."));
            return;
          }
          if (!payload) {
            const loggedOut = (xhr.responseURL || "").includes("/login");
            const failure = new Error(
              loggedOut
                ? "sesi berakhir. Muat ulang halaman lalu coba lagi."
                : `server membalas ${xhr.status}.`
            );
            failure.fatal = loggedOut;
            reject(failure);
            return;
          }
          if (!Array.isArray(payload.saved) && !Array.isArray(payload.errors)) {
            const detail =
              typeof payload.detail === "string" ? payload.detail : `server membalas ${xhr.status}.`;
            reject(new Error(detail));
            return;
          }
          resolve(payload);
        });
        xhr.addEventListener("error", () => {
          activeXhr = null;
          reject(new Error("koneksi terputus."));
        });
        xhr.addEventListener("abort", () => {
          activeXhr = null;
          reject(new Error("unggahan dibatalkan."));
        });
        xhr.send(data);
      });

    const resetControls = () => {
      driveUpload.dataset.busy = "0";
      activeXhr = null;
      if (submitBtn) {
        submitBtn.disabled = false;
        if (submitBtn.dataset.original) submitBtn.innerHTML = submitBtn.dataset.original;
      }
      if (progress) progress.hidden = true;
      if (cancelBtn) cancelBtn.hidden = true;
      if (fileInput) fileInput.disabled = false;
    };

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        if (driveUpload.dataset.busy !== "1") return;
        cancelRequested = true;
        setStatus("Membatalkan…");
        if (activeXhr) activeXhr.abort();
      });
    }

    driveUpload.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (driveUpload.dataset.busy === "1") return;
      const files = Array.from(fileInput?.files || []);
      if (!files.length) {
        setHint("Pilih minimal satu berkas dulu.");
        return;
      }

      const queue = [];
      const errors = [];
      files.forEach((file) => {
        if (maxBytes && file.size > maxBytes) {
          errors.push(
            `${file.name}: ${humanBytes(file.size)} melebihi batas ${maxMb} MB per berkas.`
          );
        } else {
          queue.push(file);
        }
      });

      driveUpload.dataset.busy = "1";
      cancelRequested = false;
      if (submitBtn) {
        submitBtn.dataset.original = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = "Mengunggah…";
      }
      if (progress) progress.hidden = false;
      if (cancelBtn) cancelBtn.hidden = false;
      if (fileInput) fileInput.disabled = true;

      const totalBytes = queue.reduce((sum, file) => sum + file.size, 0);
      let completedBytes = 0;
      let sentBytes = 0;
      let saved = 0;
      const startedAt = performance.now();

      const render = (force = false) => {
        setProgress(sentBytes, totalBytes, force);
        if (!speedEl) return;
        const elapsed = Math.max(0.2, (performance.now() - startedAt) / 1000);
        const speed = sentBytes / elapsed;
        const remaining = Math.max(0, totalBytes - sentBytes);
        const eta = speed > 0 ? Math.round(remaining / speed) : 0;
        speedEl.textContent =
          `${humanBytes(sentBytes)} / ${humanBytes(totalBytes)}` +
          ` · ${humanBytes(speed)}/dtk` +
          (remaining > 0 && eta > 0 ? ` · sisa ±${eta} dtk` : "");
      };

      setProgress(0, Math.max(1, totalBytes), true);
      setStatus(
        queue.length
          ? `Menyiapkan ${queue.length} berkas (${humanBytes(totalBytes)})…`
          : "Tidak ada berkas yang bisa diunggah."
      );
      render(true);

      for (let index = 0; index < queue.length; index += 1) {
        if (cancelRequested) break;
        const file = queue[index];
        const fileBase = completedBytes;
        setStatus(`Mengunggah ${index + 1} dari ${queue.length} — ${file.name}`);
        try {
          const result = await uploadOne(file, (loaded) => {
            sentBytes = Math.min(totalBytes, fileBase + loaded);
            render();
          });
          saved += (result.saved || []).length;
          if (Array.isArray(result.errors)) {
            errors.push(...result.errors);
            if (result.errors.length) {
              setStatus(`${index + 1} dari ${queue.length} gagal — ${file.name}`);
            }
          }
        } catch (error) {
          if (!cancelRequested) {
            errors.push(`${file.name}: ${error.message}`);
            setStatus(`${index + 1} dari ${queue.length} gagal — ${file.name}`);
          }
          if (error.fatal) {
            cancelRequested = true;
          }
        }
        completedBytes = fileBase + file.size;
        sentBytes = completedBytes;
        render(true);
      }

      setProgress(sentBytes, Math.max(1, totalBytes), true);
      setStatus(
        cancelRequested && sentBytes < totalBytes
          ? `Dibatalkan setelah ${humanBytes(sentBytes)} dari ${humanBytes(totalBytes)}.`
          : `${saved} berkas selesai diunggah.`
      );

      if (!saved) {
        const stopped = cancelRequested;
        resetControls();
        setHint(
          stopped
            ? "Unggahan dibatalkan. Tidak ada berkas yang tersimpan."
            : `Tidak ada berkas terunggah. ${errors[0] || ""}${errors.length > 1 ? ` (+${errors.length - 1} lainnya)` : ""}`.trim()
        );
        return;
      }

      try {
        sessionStorage.setItem(
          "sidewa:drive-upload",
          JSON.stringify({ saved, errors, cancelled: cancelRequested })
        );
      } catch {
        /* abaikan */
      }
      setHint(`${saved} berkas diunggah. Memuat ulang…`);
      window.setTimeout(() => window.location.reload(), 800);
    });

    if (fileInput) {
      fileInput.addEventListener("change", () => {
        if (driveUpload.dataset.busy === "1") return;
        if (!fileInput.files?.length) setHint(defaultHint);
      });
    }
  }

  /* Drive rename popover: fixed di viewport agar tidak terpotong tabel */
  const placeDriveMenu = (details) => {
    const trigger = details.querySelector("summary");
    const menu = details.querySelector(".drive-menu");
    if (!trigger || !menu) return;
    const rect = trigger.getBoundingClientRect();
    menu.style.visibility = "hidden";
    const menuRect = menu.getBoundingClientRect();
    const margin = 8;
    let left = rect.right - menuRect.width;
    left = Math.max(margin, Math.min(left, window.innerWidth - menuRect.width - margin));
    let top = rect.bottom + 6;
    if (top + menuRect.height > window.innerHeight - margin) {
      top = rect.top - menuRect.height - 6;
    }
    menu.style.left = `${left}px`;
    menu.style.top = `${Math.max(margin, top)}px`;
    menu.style.visibility = "";
  };
  document.querySelectorAll("details.drive-more").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      document.querySelectorAll("details.drive-more[open]").forEach((other) => {
        if (other !== details) other.open = false;
      });
      placeDriveMenu(details);
    });
  });
  document.addEventListener("click", (event) => {
    document.querySelectorAll("details.drive-more[open]").forEach((details) => {
      if (!details.contains(event.target)) details.open = false;
    });
  });
  window.addEventListener("resize", () => {
    document.querySelectorAll("details.drive-more[open]").forEach(placeDriveMenu);
  });
  window.addEventListener("scroll", () => {
    document.querySelectorAll("details.drive-more[open]").forEach((details) => {
      details.open = false;
    });
  }, { passive: true, capture: true });

  /* Face boxes */
  on("[data-face-toggle]", "change", (event) => {
    body.classList.toggle("show-faces", event.currentTarget.checked);
  });

  /* Lightbox */
  const lightbox = document.createElement("div");
  lightbox.className = "lightbox";
  lightbox.hidden = true;
  lightbox.innerHTML = `
    <button class="icon-btn lightbox-close" type="button" aria-label="Tutup">
      <svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg>
    </button>
    <img alt="">
    <div class="lightbox-caption"></div>`;
  document.body.appendChild(lightbox);
  const lightboxImg = lightbox.querySelector("img");
  const lightboxCaption = lightbox.querySelector(".lightbox-caption");
  const closeLightbox = () => {
    lightbox.hidden = true;
    lightboxImg.removeAttribute("src");
  };
  on("[data-lightbox]", "click", (event) => {
    const frame = event.currentTarget;
    const img = frame.querySelector("img");
    if (!img) return;
    lightboxImg.src = img.src;
    lightboxImg.alt = img.alt || "";
    lightboxCaption.textContent = frame.dataset.caption || img.alt || "";
    lightbox.hidden = false;
  });
  lightbox.querySelector(".lightbox-close").addEventListener("click", closeLightbox);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeLightbox();
      body.classList.remove("sidebar-open");
    }
  });

  /* Auto-refresh face processing */
  const processing = document.querySelector("[data-processing-url]");
  if (processing) {
    const url = processing.dataset.processingUrl;
    const label = processing.querySelector("[data-processing-text]");
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      try {
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("status");
        const data = await response.json();
        if (data.done) {
          if (attempts > 1) window.location.reload();
          return;
        }
        if (label) {
          label.textContent = `Mengenali wajah… ${data.ready} foto selesai, ${data.pending} dalam antrean.`;
        }
      } catch {
        /* diamkan, coba lagi */
      }
      if (attempts < 80) setTimeout(poll, 3000);
    };
    setTimeout(poll, 2500);
  }

  /* Submit loading */
  on("form[data-loading]", "submit", (event) => {
    const form = event.currentTarget;
    if (form.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "1";
    const button = form.querySelector('button[type="submit"]:not([data-no-loading])');
    if (button) {
      button.dataset.original = button.innerHTML;
      button.innerHTML = "Memproses…";
      button.disabled = true;
      setTimeout(() => {
        if (form.isConnected) {
          button.disabled = false;
          if (button.dataset.original) button.innerHTML = button.dataset.original;
          form.dataset.submitting = "0";
        }
      }, 12000);
    }
  });

  /* Global keyboard shortcut: / focuses search */
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      const search = document.querySelector('input[name="q"]');
      if (search) {
        event.preventDefault();
        search.focus();
      }
    }
  });

  /* Drive: ceklist (pilih banyak berkas) */
  const driveBulkForm = document.getElementById("drive-bulk-form");
  if (driveBulkForm) {
    const allHead = document.getElementById("drive-select-all-head");
    const allBar = document.getElementById("drive-select-all");
    const boxes = () => Array.from(document.querySelectorAll(".drive-select"));
    const countEl = document.getElementById("drive-bulk-count");
    const btn = document.getElementById("drive-bulk-delete");
    const update = () => {
      const checked = boxes().filter((b) => b.checked).length;
      if (countEl) countEl.textContent = checked;
      if (btn) btn.disabled = checked === 0;
      const total = boxes().length;
      const allChecked = total > 0 && checked === total;
      if (allHead) allHead.checked = allChecked;
      if (allBar) allBar.checked = allChecked;
    };
    const setAll = (state) => {
      boxes().forEach((b) => { b.checked = state; });
      update();
    };
    if (allHead) allHead.addEventListener("change", (e) => setAll(e.target.checked));
    if (allBar) allBar.addEventListener("change", (e) => setAll(e.target.checked));
    boxes().forEach((b) => b.addEventListener("change", update));
    update();
    driveBulkForm.addEventListener("submit", (e) => {
      const checked = boxes().filter((b) => b.checked).length;
      if (checked === 0) { e.preventDefault(); return; }
      const msg = driveBulkForm.getAttribute("data-confirm") || "Lanjutkan?";
      if (!window.confirm(msg)) e.preventDefault();
    });
  }

  /* Expose tiny helper for templates */
  window.SIDEWA = { toast };
})();
