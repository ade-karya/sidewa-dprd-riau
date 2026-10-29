(() => {
  "use strict";

  const root = document.querySelector("[data-guide]");
  if (!root) return;

  const slideEls = Array.from(root.querySelectorAll("[data-guide-slide]"));
  if (!slideEls.length) return;

  const slidesRoot = root.querySelector("[data-guide-slides]");
  const dotsRoot = root.querySelector("[data-guide-dots]");
  const progress = root.querySelector("[data-guide-progress]");
  const counter = root.querySelector("[data-guide-counter]");
  const live = root.querySelector("[data-guide-live]");
  const prevBtn = root.querySelector("[data-guide-prev]");
  const nextBtn = root.querySelector("[data-guide-next]");
  const nextLabel = root.querySelector("[data-guide-next-label]");
  const fullscreenBtn = root.querySelector("[data-guide-fullscreen]");
  const fullscreenIcon = fullscreenBtn ? fullscreenBtn.querySelector("use") : null;

  const aiToggle = root.querySelector("[data-guide-ai-toggle]");
  const aiPanel = root.querySelector("[data-guide-ai]");
  const aiStatus = root.querySelector("[data-guide-ai-status]");
  const aiStatusText = aiStatus ? aiStatus.querySelector("span") : null;
  const aiContext = root.querySelector("[data-guide-ai-context]");
  const aiLog = root.querySelector("[data-guide-ai-log]");
  const aiSuggestions = root.querySelector("[data-guide-ai-suggestions]");
  const aiForm = root.querySelector("[data-guide-ai-form]");
  const aiInput = root.querySelector("[data-guide-ai-input]");
  const aiSend = root.querySelector("[data-guide-ai-send]");
  const aiMic = root.querySelector("[data-guide-ai-mic]");
  const aiMute = root.querySelector("[data-guide-ai-mute]");
  const aiMinimize = root.querySelector("[data-guide-ai-minimize]");
  const aiMinimizeIcon = aiMinimize ? aiMinimize.querySelector("use") : null;
  const aiHead = root.querySelector(".guide-ai-head");
  const aiNarrate = root.querySelector("[data-guide-ai-narrate]");
  const aiReconnect = root.querySelector("[data-guide-ai-reconnect]");
  const aiMode = root.querySelector("[data-guide-ai-mode]");
  const aiHint = root.querySelector("[data-guide-ai-hint]");

  const total = slideEls.length;
  let index = 0;
  let lastFocus = null;

  /* ------------------------------------------------------------------ */
  /* Slide navigation                                                    */
  /* ------------------------------------------------------------------ */

  const dotEls = slideEls.map((slide, i) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "guide-dot";
    dot.setAttribute("aria-label", `Halaman ${i + 1}: ${slide.dataset.guideTitle || ""}`);
    dot.addEventListener("click", () => show(i));
    dotsRoot.appendChild(dot);
    return dot;
  });

  const isOpen = () => !root.hidden;
  const slideTitle = () => slideEls[index].dataset.guideTitle || "";

  function show(target) {
    index = Math.min(Math.max(target, 0), total - 1);

    slideEls.forEach((slide, i) => {
      slide.hidden = i !== index;
    });
    if (slidesRoot) slidesRoot.scrollTop = 0;

    if (progress) progress.style.width = `${((index + 1) / total) * 100}%`;
    if (counter) {
      counter.textContent = `${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}`;
    }

    dotEls.forEach((dot, i) => {
      dot.classList.toggle("is-active", i === index);
      if (i === index) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
    });

    const isLast = index === total - 1;
    if (prevBtn) prevBtn.disabled = index === 0;
    if (nextLabel) nextLabel.textContent = isLast ? "Selesai" : "Berikutnya";
    if (nextBtn) nextBtn.setAttribute("aria-label", isLast ? "Tutup panduan" : "Halaman berikutnya");
    if (live) {
      live.textContent = `Halaman ${index + 1} dari ${total}: ${slideTitle()}`;
    }
    updateAiContext();
  }

  function goNext() {
    if (index >= total - 1) closeGuide();
    else show(index + 1);
  }

  function goPrev() {
    if (index > 0) show(index - 1);
  }

  function openGuide() {
    if (isOpen()) return;
    lastFocus = document.activeElement;
    root.hidden = false;
    document.body.classList.add("guide-open");
    show(0);
    window.setTimeout(() => {
      const heading = slideEls[0].querySelector("h2");
      if (!heading) return;
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }, 80);
  }

  function closeGuide() {
    if (!isOpen()) return;
    closeAi();
    root.hidden = true;
    document.body.classList.remove("guide-open");
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
    if (lastFocus && typeof lastFocus.focus === "function") {
      lastFocus.focus({ preventScroll: true });
    }
  }

  function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else if (root.requestFullscreen) {
        root.requestFullscreen();
      }
    } catch {
      /* Layar penuh tidak tersedia — panduan tetap bisa dipakai. */
    }
  }

  function syncFullscreenState() {
    if (!fullscreenBtn) return;
    const active = document.fullscreenElement === root;
    fullscreenBtn.setAttribute(
      "aria-label",
      active ? "Keluar dari layar penuh" : "Tampilkan layar penuh"
    );
    fullscreenBtn.title = active ? "Keluar layar penuh (F)" : "Layar penuh (F)";
    if (fullscreenIcon) fullscreenIcon.setAttribute("href", active ? "#i-minimize" : "#i-maximize");
  }

  function trapFocus(event) {
    const focusable = Array.from(
      root.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')
    ).filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === root)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Gemini Live assistant                                               */
  /* ------------------------------------------------------------------ */

  const Speech = {
    socket: null,
    ready: false,
    connecting: false,
    muted: false,
    pending: "",
    voiceTurn: false,
    recording: false,
    micTimer: null,
    silenceTimer: null,
    heardSpeech: false,
    lastSoundAt: 0,
    typingRow: null,
    assistantEl: null,
    userEl: null,
    audioCtx: null,
    playbackSources: new Set(),
    playbackTime: 0,
    micCtx: null,
    micStream: null,
    micSource: null,
    micProcessor: null,
    micGain: null,
  };

  function iconNode(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.appendChild(use);
    return svg;
  }

  function scrollAiLog() {
    if (aiLog) aiLog.scrollTop = aiLog.scrollHeight;
  }

  function setAiStatus(text, state) {
    if (!aiStatus) return;
    aiStatus.className = `guide-ai-status${state ? ` is-${state}` : ""}`;
    if (aiStatusText) aiStatusText.textContent = text;
  }

  function setAiUsable(usable) {
    Speech.ready = usable;
    if (aiInput) aiInput.disabled = !usable;
    if (aiSend) aiSend.disabled = !usable;
    if (aiMic) aiMic.disabled = !usable;
  }

  function setAiMode(mode) {
    const technical = mode === "technical";
    if (aiMode) aiMode.hidden = !technical;
    if (aiPanel) aiPanel.dataset.mode = technical ? "technical" : "standard";
    if (aiHint) {
      aiHint.textContent = technical
        ? "Gemini 3.8 Live Extended Thinking · mode teknis"
        : "Gemini 3.8 Live · jawaban dapat diverifikasi";
    }
  }

  function showReconnect(visible) {
    if (aiReconnect) aiReconnect.hidden = !visible;
  }

  function updateAiContext() {
    if (aiContext) aiContext.textContent = `Halaman ${index + 1} · ${slideTitle()}`;
    signalContext();
  }

  function signalContext() {
    if (Speech.socket && Speech.socket.readyState === WebSocket.OPEN) {
      Speech.socket.send(
        JSON.stringify({ type: "context", index: index + 1, title: slideTitle() })
      );
    }
  }

  function removeTyping() {
    if (Speech.typingRow) {
      Speech.typingRow.remove();
      Speech.typingRow = null;
    }
  }

  function showTyping() {
    removeTyping();
    if (!aiLog) return;
    const row = document.createElement("div");
    row.className = "guide-ai-msg is-assistant";
    const avatar = document.createElement("span");
    avatar.className = "guide-ai-mini-avatar";
    avatar.appendChild(iconNode("sparkles"));
    const bubble = document.createElement("div");
    bubble.className = "guide-ai-bubble";
    const dots = document.createElement("span");
    dots.className = "guide-ai-typing";
    dots.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
    bubble.appendChild(dots);
    row.append(avatar, bubble);
    aiLog.appendChild(row);
    Speech.typingRow = row;
    scrollAiLog();
  }

  function addAiMessage(text, kind = "assistant") {
    if (!aiLog) return;
    removeTyping();
    const row = document.createElement("div");
    row.className = `guide-ai-msg is-${kind}`;
    if (kind !== "user") {
      const avatar = document.createElement("span");
      avatar.className = "guide-ai-mini-avatar";
      avatar.appendChild(iconNode(kind === "error" ? "alert" : "sparkles"));
      row.appendChild(avatar);
    }
    const bubble = document.createElement("div");
    bubble.className = "guide-ai-bubble";
    const p = document.createElement("p");
    p.textContent = text;
    bubble.appendChild(p);
    row.appendChild(bubble);
    aiLog.appendChild(row);
    scrollAiLog();
  }

  function ensureAssistantBubble() {
    removeTyping();
    if (Speech.assistantEl) return Speech.assistantEl;
    if (!aiLog) return null;
    const row = document.createElement("div");
    row.className = "guide-ai-msg is-assistant";
    const avatar = document.createElement("span");
    avatar.className = "guide-ai-mini-avatar";
    avatar.appendChild(iconNode("sparkles"));
    const bubble = document.createElement("div");
    bubble.className = "guide-ai-bubble";
    const p = document.createElement("p");
    bubble.appendChild(p);
    row.append(avatar, bubble);
    aiLog.appendChild(row);
    Speech.assistantEl = p;
    scrollAiLog();
    return p;
  }

  function ensureUserBubble() {
    if (Speech.userEl) return Speech.userEl;
    if (!aiLog) return null;
    const row = document.createElement("div");
    row.className = "guide-ai-msg is-user";
    const bubble = document.createElement("div");
    bubble.className = "guide-ai-bubble";
    const p = document.createElement("p");
    bubble.appendChild(p);
    row.appendChild(bubble);
    aiLog.appendChild(row);
    Speech.userEl = p;
    scrollAiLog();
    return p;
  }

  function resetTurn() {
    removeTyping();
    Speech.assistantEl = null;
    Speech.userEl = null;
    Speech.typingRow = null;
  }

  function ensureAudioContext() {
    if (!Speech.audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      Speech.audioCtx = new Ctx();
    }
    if (Speech.audioCtx.state === "suspended") {
      Speech.audioCtx.resume().catch(() => {});
    }
    return Speech.audioCtx;
  }

  function stopPlayback() {
    Speech.playbackSources.forEach((source) => {
      try {
        source.stop();
      } catch {
        /* sudah berhenti */
      }
    });
    Speech.playbackSources.clear();
    Speech.playbackTime = 0;
  }

  function playPcm(base64, rate) {
    if (Speech.muted || !base64) return;
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
      if (Speech.playbackTime < now + 0.05) Speech.playbackTime = now + 0.05;
      source.start(Speech.playbackTime);
      Speech.playbackTime += buffer.duration;
      Speech.playbackSources.add(source);
      source.onended = () => Speech.playbackSources.delete(source);
    } catch {
      /* chunk audio rusak — abaikan */
    }
  }

  function base64FromBytes(bytes) {
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  function downsample(buffer, inputRate, outputRate) {
    if (outputRate === inputRate) return buffer;
    const ratio = inputRate / outputRate;
    const length = Math.round(buffer.length / ratio);
    const result = new Float32Array(length);
    let offset = 0;
    for (let i = 0; i < length; i += 1) {
      const next = Math.min(buffer.length, Math.round((i + 1) * ratio));
      let sum = 0;
      let count = 0;
      for (let j = offset; j < next; j += 1) {
        sum += buffer[j];
        count += 1;
      }
      result[i] = count ? sum / count : 0;
      offset = next;
    }
    return result;
  }

  function stopMic(notify = true) {
    if (!Speech.recording && !Speech.micStream) return;
    Speech.recording = false;
    window.clearTimeout(Speech.micTimer);
    window.clearInterval(Speech.silenceTimer);
    Speech.micTimer = null;
    Speech.silenceTimer = null;
    if (notify && Speech.socket && Speech.socket.readyState === WebSocket.OPEN) {
      Speech.socket.send(JSON.stringify({ type: "audio_end" }));
      setAiStatus("Memproses pertanyaan…", "busy");
    }
    if (Speech.micProcessor) {
      Speech.micProcessor.onaudioprocess = null;
      try {
        Speech.micProcessor.disconnect();
      } catch {
        /* sudah terputus */
      }
    }
    if (Speech.micSource) {
      try {
        Speech.micSource.disconnect();
      } catch {
        /* sudah terputus */
      }
    }
    if (Speech.micGain) {
      try {
        Speech.micGain.disconnect();
      } catch {
        /* sudah terputus */
      }
    }
    if (Speech.micStream) {
      Speech.micStream.getTracks().forEach((track) => track.stop());
    }
    if (Speech.micCtx) {
      Speech.micCtx.close().catch(() => {});
    }
    Speech.micProcessor = null;
    Speech.micSource = null;
    Speech.micGain = null;
    Speech.micStream = null;
    Speech.micCtx = null;
    if (aiMic) {
      aiMic.classList.remove("is-recording");
      aiMic.setAttribute("aria-pressed", "false");
      aiMic.setAttribute("aria-label", "Mulai bicara ke asisten");
    }
    if (!notify && Speech.ready) setAiStatus("Siap · Gemini 3.8 Live", "ready");
  }

  async function startMic() {
    if (!Speech.ready || Speech.recording) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      addAiMessage("Browser ini tidak mendukung mikrofon. Gunakan kolom teks untuk bertanya.", "error");
      return;
    }
    stopPlayback();
    resetTurn();
    Speech.voiceTurn = true;
    Speech.heardSpeech = false;
    Speech.lastSoundAt = performance.now();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      await ctx.resume();
      const source = ctx.createMediaStreamSource(stream);
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      const silentGain = ctx.createGain();
      silentGain.gain.value = 0;
      processor.onaudioprocess = (event) => {
        if (!Speech.recording || !Speech.socket || Speech.socket.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        let energy = 0;
        for (let i = 0; i < input.length; i += 1) energy += input[i] * input[i];
        if (Math.sqrt(energy / input.length) > 0.012) {
          Speech.heardSpeech = true;
          Speech.lastSoundAt = performance.now();
        }
        const down = downsample(input, ctx.sampleRate, 16000);
        const pcm = new Int16Array(down.length);
        for (let i = 0; i < down.length; i += 1) {
          const sample = Math.max(-1, Math.min(1, down[i]));
          pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        Speech.socket.send(
          JSON.stringify({ type: "audio", data: base64FromBytes(new Uint8Array(pcm.buffer)) })
        );
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(ctx.destination);

      Speech.micCtx = ctx;
      Speech.micStream = stream;
      Speech.micSource = source;
      Speech.micProcessor = processor;
      Speech.micGain = silentGain;
      Speech.recording = true;
      Speech.micTimer = window.setTimeout(() => stopMic(true), 30000);
      Speech.silenceTimer = window.setInterval(() => {
        if (!Speech.recording) return;
        const idle = performance.now() - Speech.lastSoundAt;
        if (Speech.heardSpeech && idle > 1800) {
          stopMic(true);
        } else if (!Speech.heardSpeech && idle > 9000) {
          stopMic(true);
          addAiMessage(
            "Tidak ada suara terdeteksi. Coba lagi atau ketik pertanyaan Anda.",
            "error"
          );
        }
      }, 250);
      if (aiMic) {
        aiMic.classList.add("is-recording");
        aiMic.setAttribute("aria-pressed", "true");
        aiMic.setAttribute("aria-label", "Berhenti bicara");
      }
      signalContext();
      setAiStatus("Mendengarkan… bicara sekarang", "busy");
    } catch {
      Speech.voiceTurn = false;
      addAiMessage(
        "Mikrofon tidak dapat diakses. Izinkan akses mikrofon pada browser, lalu coba lagi.",
        "error"
      );
      setAiStatus("Izin mikrofon diperlukan", "error");
    }
  }

  function connectAi() {
    if (!Speech.socket || Speech.socket.readyState === WebSocket.CLOSED) {
      // lanjut membuat koneksi baru
    } else if (
      Speech.socket.readyState === WebSocket.OPEN ||
      Speech.socket.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    Speech.connecting = true;
    Speech.ready = false;
    setAiUsable(false);
    showReconnect(false);
    setAiStatus("Menghubungkan ke Gemini Live…", "busy");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    let socket;
    try {
      socket = new WebSocket(`${protocol}//${window.location.host}/panduan/live`);
    } catch {
      addAiMessage("Asisten AI tidak dapat dibuka pada browser ini.", "error");
      setAiStatus("Tidak tersedia", "error");
      return;
    }
    Speech.socket = socket;

    socket.addEventListener("open", () => {
      signalContext();
      setAiStatus("Menyiapkan sesi suara…", "busy");
    });

    socket.addEventListener("message", (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      handleAiPayload(payload);
    });

    socket.addEventListener("error", () => {
      if (aiPanel && !aiPanel.hidden) setAiStatus("Koneksi bermasalah", "error");
    });

    socket.addEventListener("close", (event) => {
      if (Speech.socket !== socket) return;
      Speech.socket = null;
      Speech.connecting = false;
      Speech.ready = false;
      setAiUsable(false);
      stopMic(false);
      stopPlayback();
      if (!aiPanel || aiPanel.hidden) return;
      if (event.code === 4401) {
        addAiMessage("Sesi Anda berakhir. Muat ulang halaman lalu masuk kembali untuk memakai asisten.", "error");
        setAiStatus("Sesi berakhir", "error");
      } else if (event.code === 4003) {
        addAiMessage("Asisten Live belum diaktifkan. Hubungi administrator untuk mengaktifkan Gemini Live.", "error");
        setAiStatus("Belum diaktifkan", "error");
      } else if (!event.wasClean) {
        addAiMessage("Koneksi asisten terputus. Periksa jaringan, lalu hubungkan ulang.", "error");
        setAiStatus("Terputus", "error");
      }
      showReconnect(true);
    });
  }

  function handleAiPayload(payload) {
    switch (payload.type) {
      case "ready":
        Speech.connecting = false;
        setAiUsable(true);
        setAiMode("standard");
        setAiStatus("Siap · Gemini 3.8 Live", "ready");
        showReconnect(false);
        if (Speech.pending) {
          const pending = Speech.pending;
          Speech.pending = "";
          sendQuestion(pending, pending, false);
        }
        break;
      case "mode":
        setAiMode(payload.mode);
        if (payload.mode === "technical") {
          setAiStatus("Mode teknis · Extended Thinking", "busy");
        }
        break;
      case "notice":
        if (payload.level === "info") {
          setAiStatus(payload.message, "busy");
        } else {
          addAiMessage(payload.message || "Asisten beralih mode.", "error");
          setAiStatus(payload.level === "warning" ? "Mode standar" : "Gagal", payload.level === "warning" ? "busy" : "error");
          showReconnect(payload.level !== "warning");
        }
        break;
      case "audio":
        ensureAssistantBubble();
        playPcm(payload.data, 24000);
        break;
      case "output": {
        const target = ensureAssistantBubble();
        if (target) target.textContent += payload.text || "";
        if (Speech.ready) setAiStatus("Menjelaskan…", "busy");
        scrollAiLog();
        break;
      }
      case "input":
        if (Speech.voiceTurn) {
          const userEl = ensureUserBubble();
          if (userEl) {
            userEl.textContent += payload.text || "";
            scrollAiLog();
          }
        }
        break;
      case "interrupted":
        stopPlayback();
        removeTyping();
        setAiStatus(Speech.recording ? "Mendengarkan…" : "Siap · Gemini 3.8 Live", Speech.recording ? "busy" : "ready");
        break;
      case "thinking":
        setAiStatus("Menganalisis… (Extended Thinking)", "busy");
        break;
      case "generation_complete":
        removeTyping();
        break;
      case "turn_complete":
        removeTyping();
        Speech.voiceTurn = false;
        resetTurn();
        setAiMode("standard");
        if (Speech.ready) setAiStatus("Siap · Gemini 3.8 Live", "ready");
        break;
      case "upstream_closed":
        addAiMessage(payload.message || "Koneksi asisten terputus.", "error");
        setAiStatus("Terputus", "error");
        showReconnect(true);
        break;
      case "go_away":
        showReconnect(true);
        setAiStatus("Sesi akan berakhir — hubungkan ulang", "error");
        break;
      case "error":
        addAiMessage(payload.message || "Asisten AI mengalami kendala.", "error");
        setAiStatus("Gagal", "error");
        showReconnect(true);
        break;
      default:
        break;
    }
  }

  function sendQuestion(text, displayText = text, showUser = true) {
    const question = (text || "").trim();
    if (!question) return;
    if (showUser) addAiMessage(displayText, "user");
    if (aiSuggestions) aiSuggestions.hidden = true;
    if (!Speech.ready) {
      Speech.pending = question;
      if (!Speech.socket) connectAi();
      else setAiStatus("Menyiapkan asisten…", "busy");
      return;
    }
    if (!Speech.socket || Speech.socket.readyState !== WebSocket.OPEN) {
      addAiMessage("Asisten belum terhubung. Klik “Hubungkan ulang”.", "error");
      showReconnect(true);
      return;
    }
    stopPlayback();
    resetTurn();
    Speech.voiceTurn = false;
    showTyping();
    setAiStatus("Menjawab…", "busy");
    Speech.socket.send(
      JSON.stringify({
        type: "text",
        text: question,
        index: index + 1,
        title: slideTitle(),
      })
    );
  }

  function setAiMinimized(minimized, focusInput = false) {
    if (!aiPanel) return;
    aiPanel.classList.toggle("is-minimized", minimized);
    if (aiMinimize) {
      aiMinimize.setAttribute("aria-expanded", minimized ? "false" : "true");
      aiMinimize.setAttribute(
        "aria-label",
        minimized ? "Perluas asisten AI SIDEWA" : "Ciutkan asisten AI SIDEWA"
      );
      aiMinimize.title = minimized ? "Perluas asisten" : "Ciutkan asisten";
    }
    if (aiMinimizeIcon) {
      aiMinimizeIcon.setAttribute("href", minimized ? "#i-chevron-up" : "#i-chevron-down");
    }
    if (!minimized && focusInput) {
      window.setTimeout(() => {
        if (aiInput && !aiInput.disabled) aiInput.focus({ preventScroll: true });
      }, 80);
    }
  }

  function toggleAiMinimized() {
    if (!aiPanel || aiPanel.hidden) return;
    setAiMinimized(!aiPanel.classList.contains("is-minimized"));
  }

  function openAi() {
    if (!aiPanel) return;
    setAiMinimized(false);
    aiPanel.hidden = false;
    if (aiToggle) {
      aiToggle.setAttribute("aria-expanded", "true");
      aiToggle.setAttribute("aria-label", "Tutup asisten AI SIDEWA");
    }
    updateAiContext();
    ensureAudioContext();
    connectAi();
    window.setTimeout(() => {
      if (aiInput && !aiInput.disabled) aiInput.focus({ preventScroll: true });
    }, 120);
  }

  function closeAi() {
    if (!aiPanel || aiPanel.hidden) return;
    setAiMinimized(false);
    aiPanel.hidden = true;
    if (aiToggle) {
      aiToggle.setAttribute("aria-expanded", "false");
      aiToggle.setAttribute("aria-label", "Buka asisten AI SIDEWA");
    }
    stopMic(false);
    stopPlayback();
    if (Speech.socket) {
      const socket = Speech.socket;
      Speech.socket = null;
      try {
        socket.close(1000, "panel closed");
      } catch {
        /* abaikan */
      }
    }
    Speech.pending = "";
    setAiUsable(false);
    setAiMode("standard");
    setAiStatus("Menghubungkan…", "");
    showReconnect(false);
  }

  if (aiToggle) {
    aiToggle.addEventListener("click", () => {
      if (!aiPanel) return;
      if (aiPanel.hidden) openAi();
      else if (aiPanel.classList.contains("is-minimized")) setAiMinimized(false, true);
      else closeAi();
    });
  }
  root.querySelectorAll("[data-guide-ai-close]").forEach((button) => {
    button.addEventListener("click", closeAi);
  });
  if (aiMinimize) {
    aiMinimize.addEventListener("click", toggleAiMinimized);
  }
  if (aiHead) {
    aiHead.addEventListener("click", (event) => {
      if (!aiPanel || !aiPanel.classList.contains("is-minimized")) return;
      if (event.target.closest("button")) return;
      setAiMinimized(false, true);
    });
  }
  root.querySelectorAll("[data-guide-ask]").forEach((button) => {
    button.addEventListener("click", () => sendQuestion(button.dataset.guideAsk));
  });
  if (aiForm) {
    aiForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!aiInput) return;
      const value = aiInput.value.trim();
      if (!value) return;
      aiInput.value = "";
      sendQuestion(value);
    });
  }
  if (aiMic) {
    aiMic.addEventListener("click", () => {
      if (Speech.recording) stopMic(true);
      else startMic();
    });
  }
  if (aiMute) {
    aiMute.addEventListener("click", () => {
      Speech.muted = !Speech.muted;
      aiMute.setAttribute("aria-pressed", Speech.muted ? "true" : "false");
      aiMute.setAttribute("aria-label", Speech.muted ? "Nyalakan suara asisten" : "Matikan suara asisten");
      aiMute.title = Speech.muted ? "Nyalakan suara" : "Matikan suara";
      const use = aiMute.querySelector("use");
      if (use) use.setAttribute("href", Speech.muted ? "#i-volume-off" : "#i-volume");
      if (Speech.muted) stopPlayback();
    });
  }
  if (aiNarrate) {
    aiNarrate.addEventListener("click", () => {
      if (aiPanel && aiPanel.classList.contains("is-minimized")) {
        setAiMinimized(false, true);
      }
      sendQuestion(
        "Jelaskan halaman ini kepada anggota dewan dengan bahasa presentasi yang singkat, jelas, dan meyakinkan.",
        "Jelaskan halaman ini"
      );
    });
  }
  if (aiReconnect) {
    aiReconnect.addEventListener("click", () => {
      if (Speech.socket) {
        const socket = Speech.socket;
        Speech.socket = null;
        try {
          socket.close();
        } catch {
          /* abaikan */
        }
      }
      connectAi();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Wiring                                                              */
  /* ------------------------------------------------------------------ */

  document.querySelectorAll("[data-guide-open]").forEach((button) => {
    button.addEventListener("click", openGuide);
  });
  root.querySelectorAll("[data-guide-close]").forEach((button) => {
    button.addEventListener("click", closeGuide);
  });
  root.querySelectorAll("[data-guide-next]").forEach((button) => {
    button.addEventListener("click", goNext);
  });
  root.querySelectorAll("[data-guide-prev]").forEach((button) => {
    button.addEventListener("click", goPrev);
  });
  root.querySelectorAll("[data-guide-restart]").forEach((button) => {
    button.addEventListener("click", () => show(0));
  });
  if (fullscreenBtn) fullscreenBtn.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", syncFullscreenState);
  syncFullscreenState();

  /* Keyboard navigation for presentations. */
  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    const key = event.key;
    const target = document.activeElement;
    const tag = target ? target.tagName : "";
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || (target && target.isContentEditable);

    if (key === "Escape") {
      if (typing) {
        if (target && typeof target.blur === "function") target.blur();
        return;
      }
      if (aiPanel && !aiPanel.hidden) {
        event.preventDefault();
        closeAi();
        return;
      }
      if (document.fullscreenElement) return;
      event.preventDefault();
      closeGuide();
      return;
    }
    if (typing) return;
    if (key === "Tab") {
      trapFocus(event);
      return;
    }
    if (key === "ArrowRight" || key === "PageDown" || key === " ") {
      event.preventDefault();
      goNext();
    } else if (key === "ArrowLeft" || key === "PageUp") {
      event.preventDefault();
      goPrev();
    } else if (key === "Home") {
      event.preventDefault();
      show(0);
    } else if (key === "End") {
      event.preventDefault();
      show(total - 1);
    } else if (key.toLowerCase() === "f") {
      event.preventDefault();
      toggleFullscreen();
    } else if (key.toLowerCase() === "a") {
      event.preventDefault();
      if (!aiPanel) return;
      if (aiPanel.hidden) openAi();
      else if (aiPanel.classList.contains("is-minimized")) setAiMinimized(false, true);
      else closeAi();
    }
  });

  /* Swipe between slides on touch devices. */
  let startX = 0;
  let startY = 0;
  let tracking = false;
  if (slidesRoot) {
    slidesRoot.addEventListener(
      "touchstart",
      (event) => {
        const touch = event.changedTouches[0];
        startX = touch.clientX;
        startY = touch.clientY;
        tracking = true;
      },
      { passive: true }
    );
    slidesRoot.addEventListener(
      "touchend",
      (event) => {
        if (!tracking) return;
        tracking = false;
        const touch = event.changedTouches[0];
        const dx = touch.clientX - startX;
        const dy = touch.clientY - startY;
        if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          if (dx < 0) goNext();
          else goPrev();
        }
      },
      { passive: true }
    );
  }

  /* Read-only preview from the console when presenting. */
  window.SIDEWA = Object.assign(window.SIDEWA || {}, {
    openGuide,
    closeGuide,
    goToGuideSlide: show,
    openGuideAssistant: openAi,
    closeGuideAssistant: closeAi,
  });
})();
