(() => {
  "use strict";

  // Elemen DOM
  const checkForm = document.getElementById("checkForm");
  const urlInput = document.getElementById("urlInput");
  const pasteInputBtn = document.getElementById("pasteInputBtn");
  const clearInputBtn = document.getElementById("clearInputBtn");
  const checkBtn = document.getElementById("checkBtn");
  const checkBtnSpinner = document.getElementById("checkBtnSpinner");
  const checkBtnText = document.getElementById("checkBtnText");

  const alertBox = document.getElementById("alertBox");
  const alertMessage = document.getElementById("alertMessage");

  const previewSection = document.getElementById("previewSection");
  const previewThumbnail = document.getElementById("previewThumbnail");
  const thumbnailFallback = document.getElementById("thumbnailFallback");
  const previewDuration = document.getElementById("previewDuration");
  const previewPlatform = document.getElementById("previewPlatform");
  const previewTitle = document.getElementById("previewTitle");
  const previewUploader = document.getElementById("previewUploader");

  const toggleVideoBtn = document.getElementById("toggleVideoBtn");
  const toggleAudioBtn = document.getElementById("toggleAudioBtn");
  const qualitySelect = document.getElementById("qualitySelect");
  const qualitySelectLabel = document.getElementById("qualitySelectLabel");

  const progressContainer = document.getElementById("progressContainer");
  const progressStatusText = document.getElementById("progressStatusText");
  const progressPercentText = document.getElementById("progressPercentText");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressBarTrack = document.getElementById("progressBarTrack");

  const downloadBtn = document.getElementById("downloadBtn");
  const downloadBtnIcon = document.getElementById("downloadBtnIcon");
  const downloadBtnSpinner = document.getElementById("downloadBtnSpinner");
  const downloadBtnText = document.getElementById("downloadBtnText");

  const themeToggleBtn = document.getElementById("themeToggleBtn");
  const currentYearEl = document.getElementById("currentYear");

  // State aplikasi saat ini
  let currentMediaInfo = null;
  let selectedFormat = "video"; // "video" | "audio"
  let isDownloading = false;
  let progressInterval = null;

  // Set tahun berjalan di footer
  if (currentYearEl) {
    currentYearEl.textContent = String(new Date().getFullYear());
  }

  // Pengaturan tema (otomatis mengikuti sistem, dengan opsi ganti manual)
  const savedTheme = localStorage.getItem("forte_theme");
  if (savedTheme === "dark" || savedTheme === "light") {
    document.documentElement.setAttribute("data-theme", savedTheme);
  }

  themeToggleBtn.addEventListener("click", () => {
    const root = document.documentElement;
    const currentAttr = root.getAttribute("data-theme");
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isCurrentlyDark = currentAttr ? currentAttr === "dark" : systemDark;
    const nextTheme = isCurrentlyDark ? "light" : "dark";
    root.setAttribute("data-theme", nextTheme);
    localStorage.setItem("forte_theme", nextTheme);
  });

  // Tampilkan tombol Tempel saat kosong, atau tombol Hapus saat berisi teks
  function syncInputActionButtons() {
    const hasText = urlInput.value.trim().length > 0;
    urlInput.classList.toggle("has-value", hasText);
    clearInputBtn.classList.toggle("hidden", !hasText);
    if (pasteInputBtn) {
      pasteInputBtn.classList.toggle("hidden", hasText);
    }
  }

  function extractUrlFromText(rawText) {
    if (!rawText) return "";
    const trimmed = rawText.trim();
    const urlMatch = trimmed.match(/https?:\/\/[^\s"'<>]+/i);
    return urlMatch ? urlMatch[0] : trimmed;
  }

  urlInput.addEventListener("input", syncInputActionButtons);

  // Ekstrak otomatis URL bersih jika pengguna menempel teks share dari aplikasi HP (mis. TikTok/IG yang ada caption-nya)
  urlInput.addEventListener("paste", (event) => {
    const pastedData = (event.clipboardData || window.clipboardData)?.getData("text");
    if (pastedData && /https?:\/\//i.test(pastedData) && /\s/.test(pastedData.trim())) {
      event.preventDefault();
      urlInput.value = extractUrlFromText(pastedData);
      syncInputActionButtons();
      hideAlert();
    }
  });

  if (pasteInputBtn) {
    pasteInputBtn.addEventListener("click", async () => {
      hideAlert();
      if (!navigator.clipboard || typeof navigator.clipboard.readText !== "function") {
        urlInput.focus();
        showAlert("Browser Anda tidak mengizinkan akses clipboard otomatis. Silakan tekan tahan di kolom input lalu pilih Tempel.");
        return;
      }

      try {
        const clipText = await navigator.clipboard.readText();
        const extracted = extractUrlFromText(clipText);
        if (!extracted) {
          showAlert("Clipboard masih kosong. Salin tautan video terlebih dahulu.");
          urlInput.focus();
          return;
        }
        urlInput.value = extracted;
        syncInputActionButtons();
        urlInput.focus();
      } catch (_) {
        urlInput.focus();
        showAlert("Izin baca clipboard ditolak oleh browser. Silakan tekan tahan pada kolom input lalu pilih Tempel.");
      }
    });
  }

  clearInputBtn.addEventListener("click", () => {
    urlInput.value = "";
    syncInputActionButtons();
    hideAlert();
    urlInput.focus();
  });

  syncInputActionButtons();

  function showAlert(message) {
    alertMessage.textContent = message;
    alertBox.classList.remove("hidden");
  }

  function hideAlert() {
    alertMessage.textContent = "";
    alertBox.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "";
    const mb = bytes / (1024 * 1024);
    if (mb >= 1) {
      return ` (~${mb.toFixed(1)} MB)`;
    }
    const kb = bytes / 1024;
    return ` (~${Math.round(kb)} KB)`;
  }

  function renderQualityOptions() {
    if (!currentMediaInfo) return;
    qualitySelect.innerHTML = "";

    if (selectedFormat === "video") {
      qualitySelectLabel.textContent = "Kualitas Video (MP4)";
      const qualities = currentMediaInfo.video_qualities || [
        { value: "best", label: "Terbaik otomatis" },
      ];
      qualities.forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q.value;
        const sizeHint = q.filesize_approx ? formatBytes(q.filesize_approx) : "";
        opt.textContent = `${q.label}${sizeHint}`;
        qualitySelect.appendChild(opt);
      });
    } else {
      qualitySelectLabel.textContent = "Bitrate Audio (MP3)";
      const bitrateLabels = {
        320: "320 kbps (Kualitas Terbaik)",
        256: "256 kbps (Tinggi)",
        192: "192 kbps (Standar)",
        128: "128 kbps (Ukuran Kecil)",
      };
      const bitrates = currentMediaInfo.audio_bitrates || [128, 192, 256, 320];
      [...bitrates]
        .sort((a, b) => b - a)
        .forEach((kbps) => {
          const opt = document.createElement("option");
          opt.value = String(kbps);
          opt.textContent = bitrateLabels[kbps] || `${kbps} kbps`;
          if (kbps === 192) {
            opt.selected = true;
          }
          qualitySelect.appendChild(opt);
        });
    }
  }

  function setFormat(format) {
    if (isDownloading) return;
    selectedFormat = format;
    const isVideo = format === "video";
    toggleVideoBtn.classList.toggle("active", isVideo);
    toggleVideoBtn.setAttribute("aria-selected", String(isVideo));
    toggleAudioBtn.classList.toggle("active", !isVideo);
    toggleAudioBtn.setAttribute("aria-selected", String(!isVideo));
    renderQualityOptions();
  }

  toggleVideoBtn.addEventListener("click", () => setFormat("video"));
  toggleAudioBtn.addEventListener("click", () => setFormat("audio"));

  function setCheckLoading(loading) {
    checkBtn.disabled = loading;
    urlInput.readOnly = loading;
    if (pasteInputBtn) pasteInputBtn.disabled = loading;
    if (clearInputBtn) clearInputBtn.disabled = loading;
    checkBtnSpinner.classList.toggle("hidden", !loading);
    checkBtnText.textContent = loading ? "Memeriksa..." : "Cek Video";
  }

  function updateProgressUI(percent, message) {
    const safePct = Math.max(0, Math.min(100, Math.round(percent)));
    progressStatusText.textContent = message || "Memproses...";
    progressPercentText.textContent = `${safePct}%`;
    progressBarFill.style.width = `${safePct}%`;
    progressBarTrack.setAttribute("aria-valuenow", String(safePct));
  }

  function setDownloadLoading(loading) {
    isDownloading = loading;
    downloadBtn.disabled = loading;
    checkBtn.disabled = loading;
    qualitySelect.disabled = loading;
    toggleVideoBtn.disabled = loading;
    toggleAudioBtn.disabled = loading;

    downloadBtnIcon.classList.toggle("hidden", loading);
    downloadBtnSpinner.classList.toggle("hidden", !loading);
    downloadBtnText.textContent = loading ? "Sedang Mengunduh..." : "Download";

    if (loading) {
      progressContainer.classList.remove("hidden");
      updateProgressUI(4, "Menghubungi server & menyiapkan unduhan...");
    }
  }

  function isSafeHttpUrl(url) {
    return typeof url === "string" && /^https?:\/\/[^\s"'<>]+$/i.test(url.trim());
  }

  function populatePreviewCard(data) {
    currentMediaInfo = data;
    previewPlatform.textContent = data.platform || "Video";
    previewDuration.textContent = data.duration_string || "00:00";
    previewTitle.textContent = data.title || "Tanpa Judul";
    previewUploader.textContent = data.uploader ? `Oleh ${data.uploader}` : "";

    if (data.thumbnail && isSafeHttpUrl(data.thumbnail)) {
      previewThumbnail.src = data.thumbnail;
      previewThumbnail.classList.remove("hidden");
      thumbnailFallback.classList.add("hidden");
      previewThumbnail.onerror = () => {
        previewThumbnail.classList.add("hidden");
        thumbnailFallback.classList.remove("hidden");
      };
    } else {
      previewThumbnail.removeAttribute("src");
      previewThumbnail.classList.add("hidden");
      thumbnailFallback.classList.remove("hidden");
    }

    progressContainer.classList.add("hidden");
    renderQualityOptions();
    previewSection.classList.remove("hidden");
  }

  // Handler Cek Video
  checkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isDownloading) return;

    const rawUrl = urlInput.value.trim();
    if (!rawUrl) {
      showAlert("Silakan tempel tautan video terlebih dahulu.");
      urlInput.focus();
      return;
    }

    hideAlert();
    previewSection.classList.add("hidden");
    setCheckLoading(true);

    try {
      const response = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: rawUrl }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Gagal memeriksa tautan video.");
      }

      populatePreviewCard(payload);
    } catch (err) {
      showAlert(err.message || "Terjadi gangguan jaringan saat menghubungi server.");
    } finally {
      setCheckLoading(false);
    }
  });

  function extractFilenameFromHeaders(response, fallbackExt) {
    const suggested = response.headers.get("X-Suggested-Filename");
    if (suggested) {
      try {
        return decodeURIComponent(suggested);
      } catch (_) {
        // lanjut ke Content-Disposition
      }
    }

    const disposition = response.headers.get("Content-Disposition") || "";
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match && utf8Match[1]) {
      try {
        return decodeURIComponent(utf8Match[1]);
      } catch (_) {
        // lanjut ke fallback ASCII
      }
    }

    const asciiMatch = disposition.match(/filename="([^"]+)"/i);
    if (asciiMatch && asciiMatch[1]) {
      return asciiMatch[1];
    }

    return `Forte_Media.${fallbackExt}`;
  }

  function generateTaskId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "task_" + Date.now() + "_" + Math.random().toString(36).slice(2, 10);
  }

  function startProgressPolling(taskId) {
    stopProgressPolling();
    progressInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/progress/${encodeURIComponent(taskId)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data && typeof data.percent === "number") {
          updateProgressUI(data.percent, data.message);
        }
      } catch (_) {
        // Abaikan error jaringan sementara saat polling
      }
    }, 800);
  }

  function stopProgressPolling() {
    if (progressInterval) {
      clearInterval(progressInterval);
      progressInterval = null;
    }
  }

  // Handler Download Video / MP3
  downloadBtn.addEventListener("click", async () => {
    if (!currentMediaInfo || isDownloading) return;

    hideAlert();
    const taskId = generateTaskId();
    const chosenQuality = qualitySelect.value || "best";
    const targetUrl = currentMediaInfo.webpage_url || urlInput.value.trim();

    setDownloadLoading(true);
    startProgressPolling(taskId);

    try {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: targetUrl,
          format_type: selectedFormat,
          quality: chosenQuality,
          task_id: taskId,
        }),
      });

      if (!response.ok) {
        const errPayload = await response.json().catch(() => ({}));
        throw new Error(errPayload.detail || "Gagal mengunduh file media.");
      }

      stopProgressPolling();
      updateProgressUI(96, "Menerima file ke browser Anda...");

      const blob = await response.blob();
      const ext = selectedFormat === "audio" ? "mp3" : "mp4";
      const filename = extractFilenameFromHeaders(response, ext);

      const blobUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);

      updateProgressUI(100, `Selesai! Disimpan sebagai "${filename}"`);
    } catch (err) {
      stopProgressPolling();
      progressContainer.classList.add("hidden");
      showAlert(err.message || "Gagal mengunduh media. Silakan coba lagi.");
    } finally {
      stopProgressPolling();
      setDownloadLoading(false);
    }
  });
})();

