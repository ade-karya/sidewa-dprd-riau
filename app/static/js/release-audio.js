(() => {
  "use strict";

  const root = document.querySelector("[data-release-audio]");
  if (!root) return;

  const input = root.querySelector("[data-release-audio-input]");
  const runBtn = root.querySelector("[data-release-audio-run]");
  const fileBox = root.querySelector("[data-release-audio-file]");
  const nameEl = root.querySelector("[data-release-audio-name]");
  const sizeEl = root.querySelector("[data-release-audio-size]");
  const statusEl = root.querySelector("[data-release-audio-status]");
  const savedBox = root.querySelector("[data-release-audio-saved]");
  const savedLink = root.querySelector("[data-release-audio-link]");
  const transcriptBox = root.querySelector("[data-release-audio-transcript]");
  const transcriptText = root.querySelector("[data-release-audio-transcript-text]");
  const notesEl = root.querySelector("[data-release-audio-notes]");

  const form = root.closest("form");
  const fields = {
    title: form?.querySelector("#title"),
    release_date: form?.querySelector("#release_date"),
    activity_id: form?.querySelector("#activity_id"),
    summary: form?.querySelector("#summary"),
    body: form?.querySelector("#body"),
    tags: form?.querySelector("#tags"),
  };

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const maxBytes = Number(root.dataset.maxBytes || 0);
  const maxMb = maxBytes ? Math.round(maxBytes / (1024 * 1024)) : 0;

  let busy = false;

  const formatSize = (bytes) => {
    if (!bytes) return "0 KB";
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  };

  const setStatus = (text, tone = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    if (tone) statusEl.dataset.tone = tone;
    else statusEl.removeAttribute("data-tone");
  };

  const setBusy = (value) => {
    busy = value;
    if (!runBtn) return;
    runBtn.disabled = value || !input?.files?.length;
    if (value) {
      runBtn.dataset.original = runBtn.innerHTML;
      runBtn.innerHTML = "Menyusun draf…";
    } else if (runBtn.dataset.original) {
      runBtn.innerHTML = runBtn.dataset.original;
      delete runBtn.dataset.original;
    }
  };

  const currentFile = () => input?.files?.[0] || null;

  const refreshFile = () => {
    const file = currentFile();
    if (!file) {
      if (fileBox) fileBox.hidden = true;
      if (runBtn) runBtn.disabled = true;
      setStatus(
        "Pilih rekaman terlebih dahulu. Rekaman akan disimpan di Drive pribadi Anda."
      );
      return;
    }
    if (fileBox) fileBox.hidden = false;
    if (nameEl) nameEl.textContent = file.name;
    if (sizeEl) sizeEl.textContent = formatSize(file.size);
    if (maxBytes && file.size > maxBytes) {
      if (runBtn) runBtn.disabled = true;
      setStatus(
        `Rekaman ${formatSize(file.size)} melebihi batas ${maxMb} MB. Pilih berkas lain.`,
        "danger"
      );
      return;
    }
    if (runBtn) runBtn.disabled = busy;
    setStatus(
      "Siap diproses. Rekaman disimpan ke Drive lebih dulu, lalu dikirim ke Gemini.",
      "ready"
    );
  };

  const hasContent = () =>
    Boolean(
      (fields.title?.value || "").trim() ||
        (fields.summary?.value || "").trim() ||
        (fields.body?.value || "").trim() ||
        (fields.tags?.value || "").trim()
    );

  const setValue = (field, value) => {
    if (!field || typeof value !== "string" || !value.trim()) return;
    field.value = value.trim();
  };

  const applyDraft = (draft) => {
    if (!draft) return;
    setValue(fields.title, draft.title);
    setValue(fields.summary, draft.summary);
    setValue(fields.body, draft.body);
    setValue(fields.release_date, draft.release_date);

    const tags = Array.isArray(draft.tags) ? draft.tags.filter(Boolean) : [];
    if (tags.length) {
      fields.tags.value = tags.join(", ");
    }

    const activityId = draft.activity_id;
    if (fields.activity_id && activityId !== null && activityId !== undefined) {
      const value = String(activityId);
      const option = Array.from(fields.activity_id.options).find(
        (item) => item.value === value
      );
      if (option) {
        fields.activity_id.value = value;
      }
    }

    if (transcriptBox && transcriptText && draft.transcript) {
      transcriptText.textContent = draft.transcript;
      transcriptBox.hidden = false;
    }

    if (notesEl && draft.notes) {
      notesEl.textContent = `Catatan Gemini: ${draft.notes}`;
      notesEl.hidden = false;
    }
  };

  const showDrive = (drive) => {
    if (!drive || !drive.path || !savedBox || !savedLink) return;
    savedBox.hidden = false;
    savedLink.href = drive.url || "/drive";
    savedLink.textContent = drive.path;
    savedLink.title = "Buka folder rekaman di Drive pribadi";
  };

  input?.addEventListener("change", refreshFile);

  runBtn?.addEventListener("click", async () => {
    const file = currentFile();
    if (!file || busy) return;
    if (maxBytes && file.size > maxBytes) {
      setStatus(`Rekaman melebihi batas ${maxMb} MB.`, "danger");
      return;
    }
    if (
      hasContent() &&
      !window.confirm(
        "Judul, ringkasan, isi, atau tag sudah berisi. Ganti dengan draf dari rekaman audio?"
      )
    ) {
      return;
    }

    const body = new FormData();
    body.append("audio", file, file.name);
    body.append("csrf_token", csrf);

    setBusy(true);
    setStatus("Menyimpan rekaman ke Drive pribadi Anda…", "busy");
    try {
      const response = await fetch("/rilis/draf-ai", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": csrf,
        },
        credentials: "same-origin",
        body,
      });
      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }
      if (data.drive) showDrive(data.drive);
      if (!response.ok || !data.ok) {
        throw new Error(
          data.error ||
            `Draf gagal disusun (HTTP ${response.status}). Periksa koneksi lalu coba lagi.`
        );
      }

      applyDraft(data.draft);
      const driveText = data.drive?.path
        ? `Tersimpan di Drive: ${data.drive.path}. `
        : "";
      setStatus(`${driveText}Draf terisi. Periksa kembali sebelum menyimpan.`, "success");
      window.SIDEWA?.toast?.("Draf rilis berhasil diisi dari rekaman audio.");
    } catch (error) {
      setStatus(error.message || "Draf rilis gagal disusun.", "danger");
      window.SIDEWA?.toast?.(error.message || "Draf rilis gagal disusun.");
    } finally {
      setBusy(false);
    }
  });
})();
