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

  /* Expose tiny helper for templates */
  window.SIDEWA = { toast };
})();
