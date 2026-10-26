(() => {
  "use strict";

  const facePanel = document.querySelector('[data-login-panel="face"]');
  if (!facePanel) return;

  const csrf = facePanel.dataset.csrf || "";
  const statusEl = (target) => facePanel.querySelector(`[data-face-status="${target}"]`);
  const videoEl = (target) => facePanel.querySelector(`[data-face-video="${target}"]`);
  const cameraEl = (target) => facePanel.querySelector(`[data-face-camera="${target}"]`);
  const emptyEl = (target) => facePanel.querySelector(`[data-face-empty="${target}"]`);
  const captureBtn = (target) => facePanel.querySelector(`[data-face-capture="${target}"]`);
  const startBtn = (target) => facePanel.querySelector(`[data-face-start="${target}"]`);

  const streams = {};
  const files = {};
  const previews = {};

  function setStatus(target, message, kind = "") {
    const el = statusEl(target);
    if (!el) return;
    el.textContent = message || "";
    el.className = `face-status ${kind ? `face-status-${kind}` : ""}`.trim();
  }

  function setBusy(target, busy) {
    const button = captureBtn(target);
    if (!button) return;
    if (busy) {
      button.dataset.label = button.innerHTML;
      button.innerHTML = "Memproses…";
      button.disabled = true;
    } else {
      if (button.dataset.label) button.innerHTML = button.dataset.label;
      button.disabled = !hasFrame(target);
    }
  }

  function hasFrame(target) {
    return Boolean(files[target]) || Boolean(streams[target]);
  }

  function showPreview(target, blob) {
    const camera = cameraEl(target);
    if (!camera) return;
    if (previews[target]) previews[target].remove();
    const img = document.createElement("img");
    img.className = "face-preview";
    img.alt = "Pratinjau wajah";
    img.src = URL.createObjectURL(blob);
    img.onload = () => URL.revokeObjectURL(img.src);
    camera.appendChild(img);
    previews[target] = img;
    if (emptyEl(target)) emptyEl(target).hidden = true;
    const video = videoEl(target);
    if (video) video.style.visibility = "hidden";
    if (captureBtn(target)) captureBtn(target).disabled = false;
  }

  function clearPreview(target) {
    if (previews[target]) {
      previews[target].remove();
      previews[target] = null;
    }
    const video = videoEl(target);
    if (video) video.style.visibility = "visible";
  }

  function stopCamera(target) {
    const stream = streams[target];
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      delete streams[target];
    }
    const video = videoEl(target);
    if (video) video.srcObject = null;
    if (!files[target] && emptyEl(target)) emptyEl(target).hidden = false;
  }

  async function startCamera(target) {
    setStatus(target, "");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus(
        target,
        "Kamera tidak tersedia pada perangkat/browser ini. Gunakan unggah foto atau kata sandi.",
        "danger"
      );
      return;
    }
    if (!window.isSecureContext) {
      setStatus(
        target,
        "Kamera hanya aktif pada koneksi HTTPS. Unggah foto atau gunakan kata sandi.",
        "warning"
      );
      return;
    }
    stopCamera(target);
    files[target] = null;
    clearPreview(target);
    setStatus(target, "Meminta izin kamera…");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 540 } },
        audio: false,
      });
      streams[target] = stream;
      const video = videoEl(target);
      if (video) {
        video.srcObject = stream;
        await video.play().catch(() => {});
      }
      if (emptyEl(target)) emptyEl(target).hidden = true;
      if (captureBtn(target)) captureBtn(target).disabled = false;
      setStatus(target, "Kamera aktif. Posisikan wajah di dalam bingkai.");
      startBtn(target).textContent = "Kamera aktif";
    } catch (error) {
      stopCamera(target);
      setStatus(
        target,
        "Izin kamera ditolak atau kamera tidak dapat dibuka. Gunakan unggah foto.",
        "danger"
      );
    }
  }

  function canvasBlob(target) {
    return new Promise((resolve, reject) => {
      const video = videoEl(target);
      if (!video || !video.videoWidth) {
        reject(new Error("Kamera belum siap. Coba nyalakan kamera kembali."));
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Gagal mengambil gambar."))),
        "image/jpeg",
        0.92
      );
    });
  }

  async function submit(target) {
    const endpoint =
      target === "enroll" ? "/login/wajah/daftar" : "/login/wajah";
    let blob = files[target];
    if (!blob) {
      try {
        blob = await canvasBlob(target);
      } catch (error) {
        setStatus(target, error.message, "danger");
        return;
      }
    }
    const form = new FormData();
    form.append("photo", blob, "wajah.jpg");
    form.append("csrf_token", csrf);

    if (target === "enroll") {
      const select = facePanel.querySelector("#face-member");
      const consent = facePanel.querySelector("[data-face-consent]");
      if (!select || !select.value) {
        setStatus(target, "Pilih nama Anda terlebih dahulu.", "danger");
        return;
      }
      if (!consent || !consent.checked) {
        setStatus(
          target,
          "Centang persetujuan penggunaan data biometrik terlebih dahulu.",
          "danger"
        );
        return;
      }
      form.append("member_id", select.value);
      form.append("consent", "true");
    }

    setBusy(target, true);
    setStatus(target, target === "enroll" ? "Mendaftarkan Face ID…" : "Memindai wajah…");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: form,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      let data = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }
      if (!response.ok || !data || !data.ok) {
        const detail = data && (data.error || data.detail);
        const message =
          typeof detail === "string"
            ? detail
            : "Wajah tidak dapat diproses. Coba lagi dengan foto yang lebih jelas.";
        setStatus(target, message, "danger");
        setBusy(target, false);
        return;
      }
      setStatus(
        target,
        target === "enroll"
          ? `Face ID ${data.name} berhasil didaftarkan. Mengalihkan…`
          : `Selamat datang, ${data.name}. Mengalihkan…`,
        "success"
      );
      stopCamera(target);
      window.setTimeout(() => {
        window.location.href = data.redirect || "/";
      }, 650);
    } catch (error) {
      setStatus(target, "Tidak dapat menghubungi server. Periksa koneksi Anda.", "danger");
      setBusy(target, false);
    }
  }

  /* Tab metode masuk */
  facePanel.parentElement.querySelectorAll("[data-login-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.loginTab;
      facePanel.parentElement.querySelectorAll("[data-login-tab]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      facePanel.parentElement.querySelectorAll("[data-login-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.loginPanel !== key;
      });
      if (key !== "face") {
        stopCamera("login");
        stopCamera("enroll");
      }
    });
  });

  /* Sub-tab Face ID */
  facePanel.querySelectorAll("[data-face-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.faceTab;
      facePanel.querySelectorAll("[data-face-tab]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      facePanel.querySelectorAll("[data-face-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.facePanel !== key;
      });
      if (key !== "login") stopCamera("login");
      if (key !== "enroll") stopCamera("enroll");
    });
  });

  ["login", "enroll"].forEach((target) => {
    const start = startBtn(target);
    const capture = captureBtn(target);
    if (start) start.addEventListener("click", () => startCamera(target));
    if (capture) capture.addEventListener("click", () => submit(target));

    const input = facePanel.querySelector(`[data-face-file="${target}"]`);
    if (input) {
      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        if (!file) return;
        if (!file.type.startsWith("image/")) {
          setStatus(target, "Berkas harus berupa gambar JPG, PNG, atau WEBP.", "danger");
          return;
        }
        stopCamera(target);
        files[target] = file;
        showPreview(target, file);
        setStatus(target, `Foto siap: ${file.name}. Tekan tombol untuk melanjutkan.`);
      });
    }
  });

  /* Hentikan kamera ketika halaman ditinggalkan */
  window.addEventListener("pagehide", () => {
    stopCamera("login");
    stopCamera("enroll");
  });
})();
