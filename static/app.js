/**
 * Dondu — Enterprise Media Transcoding & Downloader Engine
 * Modular Vanilla JavaScript Architecture
 */
(() => {
  "use strict";

  // --- 1. State Management ---
  const State = {
    mediaInfo: null,
    format: "video", // "video" | "audio"
    isDownloading: false,
    progressTimer: null,
    activeTaskId: null,

    reset() {
      this.mediaInfo = null;
      this.isDownloading = false;
      this.activeTaskId = null;
      if (this.progressTimer) {
        clearInterval(this.progressTimer);
        this.progressTimer = null;
      }
    },
  };

  // --- 2. DOM Elements Cache ---
  const DOM = {
    // Form & Input
    checkForm: document.getElementById("checkForm"),
    urlInput: document.getElementById("urlInput"),
    pasteInputBtn: document.getElementById("pasteInputBtn"),
    clearInputBtn: document.getElementById("clearInputBtn"),
    checkBtn: document.getElementById("checkBtn"),
    checkBtnSpinner: document.getElementById("checkBtnSpinner"),
    checkBtnText: document.getElementById("checkBtnText"),
    shortcutHint: document.getElementById("shortcutHint"),

    // Alert
    alertBox: document.getElementById("alertBox"),
    alertMessage: document.getElementById("alertMessage"),

    // Preview & Inspector
    previewSection: document.getElementById("previewSection"),
    previewThumbnail: document.getElementById("previewThumbnail"),
    thumbnailFallback: document.getElementById("thumbnailFallback"),
    previewDuration: document.getElementById("previewDuration"),
    previewPlatform: document.getElementById("previewPlatform"),
    previewTitle: document.getElementById("previewTitle"),
    previewUploader: document.getElementById("previewUploader"),
    specCodec: document.getElementById("specCodec"),
    specStatus: document.getElementById("specStatus"),

    // Controls
    toggleVideoBtn: document.getElementById("toggleVideoBtn"),
    toggleAudioBtn: document.getElementById("toggleAudioBtn"),
    qualitySelect: document.getElementById("qualitySelect"),
    qualitySelectLabel: document.getElementById("qualitySelectLabel"),

    // Progress
    progressContainer: document.getElementById("progressContainer"),
    progressStatusText: document.getElementById("progressStatusText"),
    progressPercentText: document.getElementById("progressPercentText"),
    progressBarFill: document.getElementById("progressBarFill"),
    progressBarTrack: document.getElementById("progressBarTrack"),

    // Download Button
    downloadBtn: document.getElementById("downloadBtn"),
    downloadBtnIcon: document.getElementById("downloadBtnIcon"),
    downloadBtnSpinner: document.getElementById("downloadBtnSpinner"),
    downloadBtnText: document.getElementById("downloadBtnText"),

    // Theme & Meta
    themeToggleBtn: document.getElementById("themeToggleBtn"),
    currentYear: document.getElementById("currentYear"),

    // Comments Section (Interactive Prototype)
    commentsSection: document.getElementById("commentsSection"),
    commentsCountBadge: document.getElementById("commentsCountBadge"),
    commentForm: document.getElementById("commentForm"),
    commentAuthorInput: document.getElementById("commentAuthorInput"),
    commentTextInput: document.getElementById("commentTextInput"),
    commentCharCounter: document.getElementById("commentCharCounter"),
    commentSubmitBtn: document.getElementById("commentSubmitBtn"),
    commentsList: document.getElementById("commentsList"),
  };

  // --- 3. API Client Layer ---
  const ApiClient = {
    async fetchMediaInfo(url) {
      const response = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Gagal memeriksa tautan media. Pastikan tautan valid dan publik.");
      }
      return data;
    },

    async pollProgress(taskId) {
      const res = await fetch(`/api/progress/${encodeURIComponent(taskId)}`);
      if (!res.ok) return null;
      return await res.json().catch(() => null);
    },

    async initiateDownload(url, format, quality, taskId) {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          format_type: format,
          quality,
          task_id: taskId,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Gagal memproses pengunduhan media.");
      }
      return response;
    },
  };

  // --- 4. Utilities ---
  const Utils = {
    isSafeHttpUrl(url) {
      if (typeof url !== "string") return false;
      const trimmed = url.trim();
      return /^https?:\/\/[^\s"'<>]+\.[^\s"'<>]+$/i.test(trimmed);
    },

    extractUrlFromText(rawText) {
      if (!rawText) return "";
      const trimmed = rawText.trim();
      const match = trimmed.match(/https?:\/\/[^\s"'<>]+/i);
      return match ? match[0] : trimmed;
    },

    formatBytes(bytes) {
      if (!bytes || bytes <= 0) return "";
      const mb = bytes / (1024 * 1024);
      if (mb >= 1) {
        return ` (~${mb.toFixed(1)} MB)`;
      }
      const kb = bytes / 1024;
      return ` (~${Math.round(kb)} KB)`;
    },

    generateTaskId() {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
      return "task_" + Date.now() + "_" + Math.random().toString(36).slice(2, 10);
    },

    extractFilename(response, fallbackExt) {
      const suggested = response.headers.get("X-Suggested-Filename");
      if (suggested) {
        try {
          return decodeURIComponent(suggested);
        } catch (_) {}
      }
      const disposition = response.headers.get("Content-Disposition") || "";
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match && utf8Match[1]) {
        try {
          return decodeURIComponent(utf8Match[1]);
        } catch (_) {}
      }
      const asciiMatch = disposition.match(/filename="([^"]+)"/i);
      if (asciiMatch && asciiMatch[1]) {
        return asciiMatch[1];
      }
      return `Dondu_Media.${fallbackExt}`;
    },

    escapeHtml(str) {
      if (typeof str !== "string") return "";
      return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    },

    formatTimeAgo(isoString) {
      try {
        const date = new Date(isoString);
        const now = new Date();
        const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
        if (diffSec < 60) return "Baru saja";
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `${diffMin} menit yang lalu`;
        const diffHours = Math.floor(diffMin / 60);
        if (diffHours < 24) return `${diffHours} jam yang lalu`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays} hari yang lalu`;
        return date.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
      } catch (_) {
        return "Baru saja";
      }
    },
  };

  // --- 5. UI Controller ---
  const UI = {
    init() {
      if (DOM.currentYear) {
        DOM.currentYear.textContent = String(new Date().getFullYear());
      }
      this.syncInputState();
      this.bindEvents();

      // Cek apakah link sudah ada (query param ?url= atau link yang sudah terisi di input)
      let initialUrl = "";
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const queryUrl = urlParams.get("url") || urlParams.get("link");
        if (queryUrl) {
          initialUrl = Utils.extractUrlFromText(queryUrl);
        }
      } catch (_) {}

      if (!initialUrl && DOM.urlInput && DOM.urlInput.value) {
        initialUrl = Utils.extractUrlFromText(DOM.urlInput.value);
      }

      if (initialUrl && Utils.isSafeHttpUrl(initialUrl)) {
        DOM.urlInput.value = initialUrl;
        this.syncInputState();
        this.performCheck(initialUrl);
      }
    },

    showAlert(message) {
      DOM.alertMessage.textContent = message;
      DOM.alertBox.classList.remove("hidden");
    },

    hideAlert() {
      DOM.alertMessage.textContent = "";
      DOM.alertBox.classList.add("hidden");
    },

    syncInputState() {
      const hasText = DOM.urlInput.value.trim().length > 0;
      DOM.urlInput.classList.toggle("has-value", hasText);
      DOM.clearInputBtn.classList.toggle("hidden", !hasText);
      if (DOM.pasteInputBtn) {
        DOM.pasteInputBtn.classList.toggle("hidden", hasText);
      }
    },

    setCheckLoading(loading) {
      DOM.checkBtn.disabled = loading;
      DOM.urlInput.readOnly = loading;
      if (DOM.pasteInputBtn) DOM.pasteInputBtn.disabled = loading;
      if (DOM.clearInputBtn) DOM.clearInputBtn.disabled = loading;
      DOM.checkBtnSpinner.classList.toggle("hidden", !loading);
      DOM.checkBtnText.textContent = loading ? "Memeriksa..." : "Periksa Media";
    },

    updateProgress(percent, message) {
      const safePct = Math.max(0, Math.min(100, Math.round(percent)));
      DOM.progressStatusText.textContent = message || "Memproses alur kerja...";
      DOM.progressPercentText.textContent = `${safePct}%`;
      DOM.progressBarFill.style.width = `${safePct}%`;
      DOM.progressBarTrack.setAttribute("aria-valuenow", String(safePct));
    },

    setDownloadLoading(loading) {
      State.isDownloading = loading;
      DOM.downloadBtn.disabled = loading;
      DOM.checkBtn.disabled = loading;
      DOM.qualitySelect.disabled = loading;
      DOM.toggleVideoBtn.disabled = loading;
      DOM.toggleAudioBtn.disabled = loading;

      DOM.downloadBtnIcon.classList.toggle("hidden", loading);
      DOM.downloadBtnSpinner.classList.toggle("hidden", !loading);
      DOM.downloadBtnText.textContent = loading ? "Sedang Memproses..." : "Mulai Unduh & Transcoding";

      if (loading) {
        DOM.progressContainer.classList.remove("hidden");
        this.updateProgress(4, "Menghubungi engine & menyiapkan slot pipeline...");
      }
    },

    renderQualityOptions() {
      if (!State.mediaInfo) return;
      DOM.qualitySelect.innerHTML = "";

      if (State.format === "video") {
        DOM.qualitySelectLabel.textContent = "Resolusi Video (MP4)";
        if (DOM.specCodec) DOM.specCodec.textContent = "H.264 / AAC Universal";
        const qualities = State.mediaInfo.video_qualities || [{ value: "best", label: "Resolusi Terbaik Otomatis" }];
        qualities.forEach((q) => {
          const opt = document.createElement("option");
          opt.value = q.value;
          const sizeHint = q.filesize_approx ? Utils.formatBytes(q.filesize_approx) : "";
          opt.textContent = `${q.label}${sizeHint}`;
          DOM.qualitySelect.appendChild(opt);
        });
      } else {
        DOM.qualitySelectLabel.textContent = "Bitrate Audio (MP3)";
        if (DOM.specCodec) DOM.specCodec.textContent = "MPEG Layer-3 (ID3v2)";
        const bitrateLabels = {
          320: "320 kbps (Kualitas Studio)",
          256: "256 kbps (High Fidelity)",
          192: "192 kbps (Standard)",
          128: "128 kbps (Compact)",
        };
        const bitrates = State.mediaInfo.audio_bitrates || [128, 192, 256, 320];
        [...bitrates]
          .sort((a, b) => b - a)
          .forEach((kbps) => {
            const opt = document.createElement("option");
            opt.value = String(kbps);
            opt.textContent = bitrateLabels[kbps] || `${kbps} kbps`;
            if (kbps === 192) opt.selected = true;
            DOM.qualitySelect.appendChild(opt);
          });
      }
    },

    setFormat(newFormat) {
      if (State.isDownloading) return;
      State.format = newFormat;
      const isVideo = newFormat === "video";
      DOM.toggleVideoBtn.classList.toggle("active", isVideo);
      DOM.toggleVideoBtn.setAttribute("aria-selected", String(isVideo));
      DOM.toggleAudioBtn.classList.toggle("active", !isVideo);
      DOM.toggleAudioBtn.setAttribute("aria-selected", String(!isVideo));
      DOM.progressContainer.classList.add("hidden");
      this.renderQualityOptions();
    },

    populatePreview(data) {
      State.mediaInfo = data;
      DOM.previewPlatform.textContent = (data.platform || "MEDIA").toUpperCase();
      DOM.previewDuration.textContent = data.duration_string || "00:00";
      DOM.previewTitle.textContent = data.title || "Tanpa Judul";
      DOM.previewUploader.textContent = data.uploader ? `Kreator: ${data.uploader}` : "Kreator tidak terdaftar";

      if (data.thumbnail && Utils.isSafeHttpUrl(data.thumbnail)) {
        DOM.previewThumbnail.src = data.thumbnail;
        DOM.previewThumbnail.classList.remove("hidden");
        DOM.thumbnailFallback.classList.add("hidden");
        DOM.previewThumbnail.onerror = () => {
          DOM.previewThumbnail.classList.add("hidden");
          DOM.thumbnailFallback.classList.remove("hidden");
        };
      } else {
        DOM.previewThumbnail.removeAttribute("src");
        DOM.previewThumbnail.classList.add("hidden");
        DOM.thumbnailFallback.classList.remove("hidden");
      }

      if (DOM.specStatus) {
        DOM.specStatus.textContent = "Verified & Ready";
      }

      DOM.progressContainer.classList.add("hidden");
      this.renderQualityOptions();
      DOM.previewSection.classList.remove("hidden");
    },

    async performCheck(customUrl) {
      if (State.isDownloading) return;

      const rawUrl = (typeof customUrl === "string" ? customUrl : DOM.urlInput.value).trim();
      if (!rawUrl) {
        this.showAlert("Silakan masukkan tautan media terlebih dahulu.");
        DOM.urlInput.focus();
        return;
      }

      if (DOM.urlInput.value !== rawUrl) {
        DOM.urlInput.value = rawUrl;
        this.syncInputState();
      }

      // Hindari duplikasi jika URL persis sama sudah sukses diinspeksi
      if (
        State.mediaInfo &&
        (State.mediaInfo.webpage_url || "").trim() === rawUrl &&
        !DOM.previewSection.classList.contains("hidden")
      ) {
        return;
      }

      this.hideAlert();
      DOM.previewSection.classList.add("hidden");
      this.setCheckLoading(true);

      try {
        const data = await ApiClient.fetchMediaInfo(rawUrl);
        this.populatePreview(data);
      } catch (err) {
        this.showAlert(err.message || "Gagal menghubungkan ke server engine.");
      } finally {
        this.setCheckLoading(false);
      }
    },

    bindEvents() {
      // Input typing & debounced auto-search saat link lengkap terdeteksi
      let inputDebounceTimer = null;
      DOM.urlInput.addEventListener("input", () => {
        this.syncInputState();
        const currentVal = DOM.urlInput.value.trim();

        if (State.mediaInfo && currentVal !== (State.mediaInfo.webpage_url || "").trim()) {
          DOM.previewSection.classList.add("hidden");
          DOM.progressContainer.classList.add("hidden");
          State.reset();
        }

        if (inputDebounceTimer) {
          clearTimeout(inputDebounceTimer);
          inputDebounceTimer = null;
        }

        // Jika link lengkap dan valid sudah ada/diketik, otomatis langsung mencari
        if (Utils.isSafeHttpUrl(currentVal)) {
          inputDebounceTimer = setTimeout(() => {
            if (DOM.urlInput.value.trim() === currentVal && !State.isDownloading) {
              this.performCheck(currentVal);
            }
          }, 350);
        }
      });

      // Event paste langsung pada input URL: otomatis langsung mencari
      DOM.urlInput.addEventListener("paste", (event) => {
        const text = (event.clipboardData || window.clipboardData)?.getData("text");
        if (text) {
          const extracted = Utils.extractUrlFromText(text);
          if (extracted && Utils.isSafeHttpUrl(extracted)) {
            event.preventDefault();
            DOM.urlInput.value = extracted;
            if (State.mediaInfo && extracted !== (State.mediaInfo.webpage_url || "").trim()) {
              DOM.previewSection.classList.add("hidden");
              DOM.progressContainer.classList.add("hidden");
              State.reset();
            }
            this.syncInputState();
            this.hideAlert();
            this.performCheck(extracted);
          }
        }
      });

      // Drag and drop link ke kolom input: otomatis langsung mencari
      DOM.urlInput.addEventListener("drop", (event) => {
        const text = event.dataTransfer?.getData("text");
        if (text) {
          const extracted = Utils.extractUrlFromText(text);
          if (extracted && Utils.isSafeHttpUrl(extracted)) {
            event.preventDefault();
            DOM.urlInput.value = extracted;
            this.syncInputState();
            this.hideAlert();
            this.performCheck(extracted);
          }
        }
      });

      // Tombol Tempel (Paste Button): ambil dari clipboard & langsung mencari
      if (DOM.pasteInputBtn) {
        DOM.pasteInputBtn.addEventListener("click", async () => {
          this.hideAlert();
          if (!navigator.clipboard || typeof navigator.clipboard.readText !== "function") {
            DOM.urlInput.focus();
            this.showAlert("Akses clipboard browser tidak tersedia. Silakan gunakan shortcut Ctrl+V atau klik kanan Tempel.");
            return;
          }
          try {
            const clipText = await navigator.clipboard.readText();
            const extracted = Utils.extractUrlFromText(clipText);
            if (!extracted) {
              this.showAlert("Clipboard kosong. Salin tautan media terlebih dahulu.");
              DOM.urlInput.focus();
              return;
            }
            DOM.urlInput.value = extracted;
            if (State.mediaInfo && extracted !== (State.mediaInfo.webpage_url || "").trim()) {
              DOM.previewSection.classList.add("hidden");
              DOM.progressContainer.classList.add("hidden");
              State.reset();
            }
            this.syncInputState();
            if (Utils.isSafeHttpUrl(extracted)) {
              this.performCheck(extracted);
            } else {
              DOM.urlInput.focus();
            }
          } catch (_) {
            DOM.urlInput.focus();
            this.showAlert("Izin akses clipboard ditolak. Silakan tempel secara manual.");
          }
        });
      }

      DOM.clearInputBtn.addEventListener("click", () => {
        if (inputDebounceTimer) {
          clearTimeout(inputDebounceTimer);
          inputDebounceTimer = null;
        }
        DOM.urlInput.value = "";
        this.hideAlert();
        DOM.previewSection.classList.add("hidden");
        DOM.progressContainer.classList.add("hidden");
        State.reset();
        this.syncInputState();
        DOM.urlInput.focus();
      });

      // Format switchers
      DOM.toggleVideoBtn.addEventListener("click", () => this.setFormat("video"));
      DOM.toggleAudioBtn.addEventListener("click", () => this.setFormat("audio"));

      // Quality selector change resets prior progress completion banner
      DOM.qualitySelect.addEventListener("change", () => {
        if (!State.isDownloading) {
          DOM.progressContainer.classList.add("hidden");
        }
      });

      // Form submission (Enter key / manual click)
      DOM.checkForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.performCheck();
      });

      // Download trigger
      DOM.downloadBtn.addEventListener("click", async () => {
        if (!State.mediaInfo || State.isDownloading) return;

        this.hideAlert();
        const taskId = Utils.generateTaskId();
        State.activeTaskId = taskId;
        const chosenQuality = DOM.qualitySelect.value || "best";
        const targetUrl = State.mediaInfo.webpage_url || DOM.urlInput.value.trim();

        this.setDownloadLoading(true);
        this.startPolling(taskId);

        try {
          const response = await ApiClient.initiateDownload(targetUrl, State.format, chosenQuality, taskId);

          this.stopPolling();

          let blob;
          const contentLength = response.headers.get("Content-Length");
          const totalBytes = contentLength ? parseInt(contentLength, 10) : 0;

          if (response.body && totalBytes > 0 && typeof ReadableStream !== "undefined") {
            const reader = response.body.getReader();
            let receivedBytes = 0;
            const chunks = [];
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              chunks.push(value);
              receivedBytes += value.length;
              const streamPct = 85 + Math.round((receivedBytes / totalBytes) * 14);
              const mbDone = (receivedBytes / (1024 * 1024)).toFixed(1);
              const mbTotal = (totalBytes / (1024 * 1024)).toFixed(1);
              this.updateProgress(streamPct, `Mentransfer file (${mbDone} MB / ${mbTotal} MB)...`);
            }
            blob = new Blob(chunks, { type: response.headers.get("Content-Type") || "application/octet-stream" });
          } else {
            this.updateProgress(94, "Menerima aliran data ke browser...");
            blob = await response.blob();
          }

          const ext = State.format === "audio" ? "mp3" : "mp4";
          const filename = Utils.extractFilename(response, ext);

          const blobUrl = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = blobUrl;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);

          this.updateProgress(100, `Transcoding selesai. Disimpan sebagai "${filename}"`);
        } catch (err) {
          this.stopPolling();
          DOM.progressContainer.classList.add("hidden");
          this.showAlert(err.message || "Gagal memproses alur kerja unduhan.");
        } finally {
          this.stopPolling();
          this.setDownloadLoading(false);
        }
      });
    },

    startPolling(taskId) {
      this.stopPolling();
      State.progressTimer = setInterval(async () => {
        try {
          const data = await ApiClient.pollProgress(taskId);
          if (data && typeof data.percent === "number") {
            this.updateProgress(data.percent, data.message);
          }
        } catch (_) {}
      }, 750);
    },

    stopPolling() {
      if (State.progressTimer) {
        clearInterval(State.progressTimer);
        State.progressTimer = null;
      }
    },
  };

  // --- 6. Global Keyboard Shortcuts ---
  const Shortcuts = {
    init() {
      const isMac = typeof navigator !== "undefined" && /(Mac|iPhone|iPod|iPad)/i.test(navigator.platform || navigator.userAgent);
      if (DOM.shortcutHint && isMac) {
        DOM.shortcutHint.innerHTML = "<kbd>⌘V</kbd> tempel otomatis";
      }

      window.addEventListener("keydown", (e) => {
        // Focus search/URL input with / or Ctrl+K / Cmd+K
        if ((e.key === "/" || ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K"))) && document.activeElement !== DOM.urlInput) {
          e.preventDefault();
          DOM.urlInput.focus();
          DOM.urlInput.select();
          return;
        }

        // Global Ctrl+V / Cmd+V auto-focus, clipboard read, & auto search
        if ((e.ctrlKey || e.metaKey) && (e.key === "v" || e.key === "V")) {
          // Jika fokus sedang di textarea atau input lain (seperti komentar), biarkan perilaku bawaan
          if (
            document.activeElement &&
            (document.activeElement.tagName === "TEXTAREA" ||
              (document.activeElement.tagName === "INPUT" && document.activeElement !== DOM.urlInput))
          ) {
            return;
          }

          if (document.activeElement !== DOM.urlInput) {
            DOM.urlInput.focus();
            if (navigator.clipboard && typeof navigator.clipboard.readText === "function") {
              navigator.clipboard.readText().then((clipText) => {
                const extracted = Utils.extractUrlFromText(clipText);
                if (extracted) {
                  DOM.urlInput.value = extracted;
                  if (State.mediaInfo && extracted !== (State.mediaInfo.webpage_url || "").trim()) {
                    DOM.previewSection.classList.add("hidden");
                    DOM.progressContainer.classList.add("hidden");
                    State.reset();
                  }
                  UI.syncInputState();
                  UI.hideAlert();
                  if (Utils.isSafeHttpUrl(extracted)) {
                    UI.performCheck(extracted);
                  }
                }
              }).catch(() => {
                // Izin clipboard mungkin memerlukan interaksi pengguna; fokus sudah di urlInput
              });
            }
          }
          return;
        }

        // Esc to clear input, hide preview, & dismiss alert
        if (e.key === "Escape") {
          if (!State.isDownloading) {
            UI.hideAlert();
            if (document.activeElement === DOM.urlInput) {
              DOM.urlInput.value = "";
              DOM.previewSection.classList.add("hidden");
              DOM.progressContainer.classList.add("hidden");
              State.reset();
              UI.syncInputState();
            }
          }
        }
      });
    },
  };

  // --- 7. Theme Controller ---
  const ThemeManager = {
    STORAGE_KEY: "dondu_theme",

    init() {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      if (saved === "dark" || saved === "light") {
        document.documentElement.setAttribute("data-theme", saved);
      }

      DOM.themeToggleBtn.addEventListener("click", () => {
        const root = document.documentElement;
        const current = root.getAttribute("data-theme");
        const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        const isDark = current ? current === "dark" : systemDark;
        const next = isDark ? "light" : "dark";
        root.setAttribute("data-theme", next);
        localStorage.setItem(this.STORAGE_KEY, next);
      });
    },
  };

  // --- 8. Device Analytics Tracking ---
  const DeviceTracker = {
    STORAGE_KEY: "dondu_device_uuid",

    getDeviceId() {
      let id = localStorage.getItem(this.STORAGE_KEY);
      if (!id) {
        id = Utils.generateTaskId();
        localStorage.setItem(this.STORAGE_KEY, id);
      }
      return id;
    },

    init() {
      try {
        const deviceId = this.getDeviceId();
        const payload = {
          device_id: deviceId,
          user_agent: navigator.userAgent || "",
          platform: navigator.platform || "",
          screen_res: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
          language: navigator.language || "",
        };

        fetch("/api/track-device", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).catch(() => {});
      } catch (_) {}
    },
  };

  // --- 9. Comments Module (Interactive & Persistent Engine) ---
  const CommentsManager = {
    STORAGE_KEY: "dondu_comments_v1",

    defaultComments: [
      {
        id: "c_1",
        author: "FarreL",
        badge: "Developer",
        text: "Sistem pipeline Dondu v2.0 stabil. Kecepatan transcode H.264 & audio MP3 berjalan normal tanpa kompresi berlebih. Silakan tinggalkan kritik atau saran di sini!",
        timestamp: new Date(Date.now() - 3600 * 1000 * 2).toISOString(),
      },
      {
        id: "c_2",
        author: "Alex Pratama",
        badge: "User",
        text: "UI-nya bersih banget tanpa gradasi dan warna terracotta-nya enak di mata. Unduh video TikTok jernih langsung masuk tanpa watermark.",
        timestamp: new Date(Date.now() - 3600 * 1000 * 5).toISOString(),
      },
      {
        id: "c_3",
        author: "Rian Saputra",
        badge: "",
        text: "Fitur keyboard shortcut Ctrl+V sangat membantu buat paste cepat. Mantap!",
        timestamp: new Date(Date.now() - 3600 * 1000 * 24).toISOString(),
      },
    ],

    async init() {
      if (!DOM.commentForm || !DOM.commentsList) return;
      this.bindEvents();
      this.render();
      await this.fetchServerComments();
    },

    async fetchServerComments() {
      try {
        const res = await fetch("/api/comments");
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.comments) && data.comments.length > 0) {
            const normalized = data.comments.map((c) => ({
              id: c.id,
              author: c.author,
              badge: c.badge || "",
              text: c.text,
              timestamp: c.created_at,
              isPinned: Boolean(c.is_pinned),
            }));
            this.saveComments(normalized);
            this.render();
          }
        }
      } catch (_) {}
    },

    getComments() {
      try {
        const raw = localStorage.getItem(this.STORAGE_KEY);
        if (!raw) {
          this.saveComments(this.defaultComments);
          return [...this.defaultComments];
        }
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      } catch (_) {}
      return [...this.defaultComments];
    },

    saveComments(comments) {
      try {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(comments));
      } catch (_) {}
    },

    bindEvents() {
      if (DOM.commentTextInput && DOM.commentCharCounter) {
        DOM.commentTextInput.addEventListener("input", () => {
          const len = DOM.commentTextInput.value.length;
          DOM.commentCharCounter.textContent = `${len} / 500`;
        });
      }

      DOM.commentForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const author = (DOM.commentAuthorInput?.value || "").trim();
        const text = (DOM.commentTextInput?.value || "").trim();

        if (!author) {
          DOM.commentAuthorInput?.focus();
          return;
        }

        if (!text) {
          DOM.commentTextInput?.focus();
          return;
        }

        const deviceId = DeviceTracker.getDeviceId();
        const newComment = {
          id: "c_" + Date.now(),
          author: author.slice(0, 50),
          badge: "",
          text: text.slice(0, 500),
          timestamp: new Date().toISOString(),
          device_id: deviceId,
        };

        const list = this.getComments();
        list.unshift(newComment);
        this.saveComments(list);

        if (DOM.commentTextInput) {
          DOM.commentTextInput.value = "";
        }
        if (DOM.commentCharCounter) {
          DOM.commentCharCounter.textContent = "0 / 500";
        }

        this.render();

        // Kirim ke server API secara persisten
        try {
          await fetch("/api/comments", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              author: newComment.author,
              text: newComment.text,
              device_id: deviceId,
            }),
          });
          await this.fetchServerComments();
        } catch (_) {}
      });
    },

    getInitials(name) {
      if (!name) return "U";
      const parts = name.trim().split(/\s+/);
      if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
      }
      return name.slice(0, 2).toUpperCase();
    },

    render() {
      const list = this.getComments();
      if (DOM.commentsCountBadge) {
        DOM.commentsCountBadge.textContent = String(list.length);
      }

      if (!DOM.commentsList) return;

      if (list.length === 0) {
        DOM.commentsList.innerHTML = `
          <div class="comments-empty">
            Belum ada komentar. Jadilah yang pertama memberikan ulasan!
          </div>
        `;
        return;
      }

      const fragment = document.createDocumentFragment();
      list.forEach((c) => {
        const item = document.createElement("div");
        item.className = "comment-item";

        const initials = Utils.escapeHtml(this.getInitials(c.author));
        const authorSafe = Utils.escapeHtml(c.author);
        const textSafe = Utils.escapeHtml(c.text);
        const timeFormatted = Utils.formatTimeAgo(c.timestamp);
        const badgeHtml = c.badge
          ? `<span class="comment-badge-author">${Utils.escapeHtml(c.badge)}</span>`
          : "";

        item.innerHTML = `
          <div class="comment-avatar" aria-hidden="true">${initials}</div>
          <div class="comment-body">
            <div class="comment-meta">
              <span class="comment-author">${authorSafe}${badgeHtml}</span>
              <time class="comment-time" datetime="${Utils.escapeHtml(c.timestamp || "")}">${timeFormatted}</time>
            </div>
            <p class="comment-text">${textSafe}</p>
          </div>
        `;
        fragment.appendChild(item);
      });

      DOM.commentsList.innerHTML = "";
      DOM.commentsList.appendChild(fragment);
    },
  };

  // --- Application Bootstrap ---
  DeviceTracker.init();
  ThemeManager.init();
  Shortcuts.init();
  UI.init();
  CommentsManager.init();
})();
