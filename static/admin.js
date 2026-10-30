/**
 * Dondu Central Command (/DonduFarrel)
 * Administration & Device Analytics Controller
 */
(() => {
  "use strict";

  const STORAGE_KEY = "dondu_admin_key";

  const DOM = {
    authSection: document.getElementById("authSection"),
    dashboardMain: document.getElementById("dashboardMain"),
    adminLoginForm: document.getElementById("adminLoginForm"),
    adminPasskeyInput: document.getElementById("adminPasskeyInput"),
    authAlert: document.getElementById("authAlert"),
    authAlertText: document.getElementById("authAlertText"),

    // Metrics
    metricTotalDevices: document.getElementById("metricTotalDevices"),
    metricTotalVisits: document.getElementById("metricTotalVisits"),
    metricDevicesToday: document.getElementById("metricDevicesToday"),
    metricTotalComments: document.getElementById("metricTotalComments"),

    // Breakdown Lists
    deviceTypeDistList: document.getElementById("deviceTypeDistList"),
    osDistList: document.getElementById("osDistList"),
    browserDistList: document.getElementById("browserDistList"),

    // Tables
    devicesTableBody: document.getElementById("devicesTableBody"),
    commentsTableBody: document.getElementById("commentsTableBody"),

    // Modal
    commentModal: document.getElementById("commentModal"),
    modalTitle: document.getElementById("modalTitle"),
    commentEditForm: document.getElementById("commentEditForm"),
    modalCommentId: document.getElementById("modalCommentId"),
    modalAuthorInput: document.getElementById("modalAuthorInput"),
    modalBadgeInput: document.getElementById("modalBadgeInput"),
    modalTextInput: document.getElementById("modalTextInput"),
    modalPinCheckbox: document.getElementById("modalPinCheckbox"),
    modalActiveCheckbox: document.getElementById("modalActiveCheckbox"),
    btnModalClose: document.getElementById("btnModalClose"),
    btnModalCancel: document.getElementById("btnModalCancel"),
    btnAddAnnouncement: document.getElementById("btnAddAnnouncement"),

    // Theme
    themeToggleBtn: document.getElementById("themeToggleBtn"),
  };

  const AdminState = {
    adminKey: sessionStorage.getItem(STORAGE_KEY) || localStorage.getItem(STORAGE_KEY) || "",
    comments: [],
    analytics: null,
  };

  const Utils = {
    escapeHtml(str) {
      if (typeof str !== "string") return "";
      return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    },

    formatDate(isoString) {
      if (!isoString) return "-";
      try {
        const d = new Date(isoString);
        return d.toLocaleString("id-ID", {
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
      } catch (_) {
        return isoString;
      }
    },
  };

  const AdminApi = {
    getHeaders() {
      return {
        "Content-Type": "application/json",
        "X-Admin-Key": AdminState.adminKey,
      };
    },

    async login(passkey) {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passkey }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Passkey salah.");
      }
      return await res.json();
    },

    async fetchAnalytics() {
      const res = await fetch("/api/admin/analytics", {
        headers: this.getHeaders(),
      });
      if (!res.ok) throw new Error("Gagal memuat analitik");
      return await res.json();
    },

    async fetchComments() {
      const res = await fetch("/api/admin/comments", {
        headers: this.getHeaders(),
      });
      if (!res.ok) throw new Error("Gagal memuat daftar komentar");
      const data = await res.json();
      return data.comments || [];
    },

    async createComment(author, text) {
      const res = await fetch("/api/admin/comments", {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ author, text }),
      });
      if (!res.ok) throw new Error("Gagal menambahkan komentar resmi");
      return await res.json();
    },

    async updateComment(id, payload) {
      const res = await fetch(`/api/admin/comments/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: this.getHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Gagal memperbarui komentar");
      return await res.json();
    },

    async deleteComment(id) {
      const res = await fetch(`/api/admin/comments/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: this.getHeaders(),
      });
      if (!res.ok) throw new Error("Gagal menghapus komentar");
      return await res.json();
    },
  };

  const AdminUI = {
    init() {
      this.bindTheme();
      this.bindEvents();

      if (AdminState.adminKey) {
        this.verifyAndLoad();
      } else {
        this.showLogin();
      }
    },

    showLogin() {
      DOM.authSection.classList.remove("hidden");
      DOM.dashboardMain.classList.add("hidden");
      DOM.adminPasskeyInput?.focus();
    },

    showDashboard() {
      DOM.authSection.classList.add("hidden");
      DOM.dashboardMain.classList.remove("hidden");
    },

    showAlert(msg) {
      DOM.authAlertText.textContent = msg;
      DOM.authAlert.classList.remove("hidden");
    },

    hideAlert() {
      DOM.authAlertText.textContent = "";
      DOM.authAlert.classList.add("hidden");
    },

    async verifyAndLoad() {
      try {
        await Promise.all([this.loadAnalytics(), this.loadComments()]);
        this.showDashboard();
      } catch (err) {
        sessionStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STORAGE_KEY);
        AdminState.adminKey = "";
        this.showLogin();
        this.showAlert("Sesi admin berakhir atau passkey tidak valid.");
      }
    },

    async loadAnalytics() {
      const data = await AdminApi.fetchAnalytics();
      AdminState.analytics = data;

      DOM.metricTotalDevices.textContent = String(data.total_devices || 0);
      DOM.metricTotalVisits.textContent = String(data.total_visits || 0);
      DOM.metricDevicesToday.textContent = String(data.devices_today || 0);
      DOM.metricTotalComments.textContent = String(data.total_comments || 0);

      this.renderDistribution(DOM.deviceTypeDistList, data.device_type_breakdown, "type");
      this.renderDistribution(DOM.osDistList, data.os_breakdown, "os");
      this.renderDistribution(DOM.browserDistList, data.browser_breakdown, "browser");
      this.renderDevicesTable(data.recent_devices || []);
    },

    renderDistribution(container, list, keyName) {
      if (!container) return;
      if (!list || list.length === 0) {
        container.innerHTML = '<span style="font-size:0.8rem; color:var(--text-muted);">Belum ada data</span>';
        return;
      }
      container.innerHTML = list
        .map(
          (item) => `
          <div class="distribution-item">
            <span class="distribution-name">${Utils.escapeHtml(item[keyName] || "Unknown")}</span>
            <span class="distribution-count">${item.count}</span>
          </div>
        `
        )
        .join("");
    },

    renderDevicesTable(devices) {
      if (!DOM.devicesTableBody) return;
      if (devices.length === 0) {
        DOM.devicesTableBody.innerHTML = `
          <tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:24px;">Belum ada perangkat yang tercatat. Kunjungi halaman utama untuk menguji.</td></tr>
        `;
        return;
      }

      DOM.devicesTableBody.innerHTML = devices
        .map((d) => {
          const shortId = d.device_id.length > 16 ? d.device_id.slice(0, 14) + "..." : d.device_id;
          return `
            <tr>
              <td><code title="${Utils.escapeHtml(d.device_id)}">${Utils.escapeHtml(shortId)}</code></td>
              <td><span class="pill-badge">${Utils.escapeHtml(d.device_type || "Desktop")}</span></td>
              <td><strong>${Utils.escapeHtml(d.os || "Unknown")}</strong></td>
              <td>${Utils.escapeHtml(d.browser || "Unknown")}</td>
              <td><span style="font-size:0.8rem; color:var(--text-secondary);">${Utils.escapeHtml(d.screen_res || "-")}</span></td>
              <td><strong>${d.visit_count || 1}x</strong></td>
              <td><span style="font-size:0.8rem; color:var(--text-muted);">${Utils.formatDate(d.last_seen_at)}</span></td>
            </tr>
          `;
        })
        .join("");
    },

    async loadComments() {
      const comments = await AdminApi.fetchComments();
      AdminState.comments = comments;
      this.renderCommentsTable(comments);
    },

    renderCommentsTable(comments) {
      if (!DOM.commentsTableBody) return;
      if (comments.length === 0) {
        DOM.commentsTableBody.innerHTML = `
          <tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:24px;">Belum ada komentar tersimpan.</td></tr>
        `;
        return;
      }

      DOM.commentsTableBody.innerHTML = comments
        .map((c) => {
          const isPinned = Boolean(c.is_pinned);
          const isHidden = c.status === "hidden";
          const statusPill = isPinned
            ? '<span class="pill-status pill-pinned">PINNED</span>'
            : isHidden
            ? '<span class="pill-status pill-hidden">HIDDEN</span>'
            : '<span class="pill-status pill-active">ACTIVE</span>';

          const badgePill = c.badge ? `<span class="pill-badge">${Utils.escapeHtml(c.badge)}</span>` : "-";

          return `
            <tr data-id="${Utils.escapeHtml(c.id)}">
              <td><strong>${Utils.escapeHtml(c.author)}</strong></td>
              <td>${badgePill}</td>
              <td style="max-width:320px; word-break:break-word;">${Utils.escapeHtml(c.text)}</td>
              <td><span style="font-size:0.78rem; color:var(--text-muted);">${Utils.formatDate(c.created_at)}</span></td>
              <td>${statusPill}</td>
              <td>${isPinned ? "📌 Ya" : "—"}</td>
              <td>
                <div class="table-actions">
                  <button type="button" class="btn-action btn-edit" data-id="${Utils.escapeHtml(c.id)}" title="Edit komentar">
                    Edit
                  </button>
                  <button type="button" class="btn-action btn-toggle-pin" data-id="${Utils.escapeHtml(c.id)}" data-pinned="${isPinned ? "1" : "0"}" title="Toggle Pin">
                    ${isPinned ? "Unpin" : "Pin"}
                  </button>
                  <button type="button" class="btn-action btn-toggle-status" data-id="${Utils.escapeHtml(c.id)}" data-status="${Utils.escapeHtml(c.status)}" title="Sembunyikan/Tampilkan">
                    ${isHidden ? "Tampilkan" : "Sembunyikan"}
                  </button>
                  <button type="button" class="btn-action btn-action-delete btn-delete" data-id="${Utils.escapeHtml(c.id)}" title="Hapus permanen">
                    Hapus
                  </button>
                </div>
              </td>
            </tr>
          `;
        })
        .join("");
    },

    openModal(comment = null) {
      if (comment) {
        DOM.modalTitle.textContent = "Edit Komentar #" + comment.id;
        DOM.modalCommentId.value = comment.id;
        DOM.modalAuthorInput.value = comment.author;
        DOM.modalBadgeInput.value = comment.badge || "";
        DOM.modalTextInput.value = comment.text;
        DOM.modalPinCheckbox.checked = Boolean(comment.is_pinned);
        DOM.modalActiveCheckbox.checked = comment.status !== "hidden";
      } else {
        DOM.modalTitle.textContent = "Tambah Komentar / Pengumuman Resmi";
        DOM.modalCommentId.value = "";
        DOM.modalAuthorInput.value = "FarreL (Dev)";
        DOM.modalBadgeInput.value = "Developer";
        DOM.modalTextInput.value = "";
        DOM.modalPinCheckbox.checked = true;
        DOM.modalActiveCheckbox.checked = true;
      }
      DOM.commentModal.classList.remove("hidden");
      DOM.modalTextInput.focus();
    },

    closeModal() {
      DOM.commentModal.classList.add("hidden");
    },

    bindEvents() {
      // Login Form
      DOM.adminLoginForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pass = DOM.adminPasskeyInput.value.trim();
        if (!pass) return;

        this.hideAlert();
        try {
          const res = await AdminApi.login(pass);
          AdminState.adminKey = res.token || pass;
          sessionStorage.setItem(STORAGE_KEY, AdminState.adminKey);
          localStorage.setItem(STORAGE_KEY, AdminState.adminKey);
          await this.verifyAndLoad();
        } catch (err) {
          this.showAlert(err.message || "Passkey salah.");
        }
      });

      // Add Announcement Button
      DOM.btnAddAnnouncement?.addEventListener("click", () => {
        this.openModal(null);
      });

      // Modal Close
      DOM.btnModalClose?.addEventListener("click", () => this.closeModal());
      DOM.btnModalCancel?.addEventListener("click", () => this.closeModal());
      DOM.commentModal?.addEventListener("click", (e) => {
        if (e.target === DOM.commentModal) this.closeModal();
      });

      // Modal Submit (Create or Update)
      DOM.commentEditForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const cid = DOM.modalCommentId.value;
        const author = DOM.modalAuthorInput.value.trim();
        const badge = DOM.modalBadgeInput.value.trim();
        const text = DOM.modalTextInput.value.trim();
        const isPinned = DOM.modalPinCheckbox.checked;
        const status = DOM.modalActiveCheckbox.checked ? "active" : "hidden";

        if (!author || !text) return;

        try {
          if (cid) {
            // Update
            await AdminApi.updateComment(cid, {
              author,
              badge,
              text,
              is_pinned: isPinned,
              status,
            });
          } else {
            // Create
            await AdminApi.createComment(author, text);
          }
          this.closeModal();
          await this.loadComments();
          await this.loadAnalytics();
        } catch (err) {
          alert("Gagal menyimpan komentar: " + err.message);
        }
      });

      // Table Action Delegations
      DOM.commentsTableBody?.addEventListener("click", async (e) => {
        const btnEdit = e.target.closest(".btn-edit");
        const btnPin = e.target.closest(".btn-toggle-pin");
        const btnStatus = e.target.closest(".btn-toggle-status");
        const btnDelete = e.target.closest(".btn-delete");

        if (btnEdit) {
          const cid = btnEdit.dataset.id;
          const found = AdminState.comments.find((c) => c.id === cid);
          if (found) this.openModal(found);
          return;
        }

        if (btnPin) {
          const cid = btnPin.dataset.id;
          const currentPinned = btnPin.dataset.pinned === "1";
          try {
            await AdminApi.updateComment(cid, { is_pinned: !currentPinned });
            await this.loadComments();
          } catch (err) {
            alert(err.message);
          }
          return;
        }

        if (btnStatus) {
          const cid = btnStatus.dataset.id;
          const currentStatus = btnStatus.dataset.status;
          const nextStatus = currentStatus === "hidden" ? "active" : "hidden";
          try {
            await AdminApi.updateComment(cid, { status: nextStatus });
            await this.loadComments();
          } catch (err) {
            alert(err.message);
          }
          return;
        }

        if (btnDelete) {
          const cid = btnDelete.dataset.id;
          if (confirm("Apakah Anda yakin ingin menghapus komentar ini secara permanen?")) {
            try {
              await AdminApi.deleteComment(cid);
              await this.loadComments();
              await this.loadAnalytics();
            } catch (err) {
              alert(err.message);
            }
          }
        }
      });
    },

    bindTheme() {
      const saved = localStorage.getItem("dondu_theme");
      if (saved === "dark" || saved === "light") {
        document.documentElement.setAttribute("data-theme", saved);
      }

      DOM.themeToggleBtn?.addEventListener("click", () => {
        const root = document.documentElement;
        const current = root.getAttribute("data-theme");
        const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        const isDark = current ? current === "dark" : systemDark;
        const next = isDark ? "light" : "dark";
        root.setAttribute("data-theme", next);
        localStorage.setItem("dondu_theme", next);
      });
    },
  };

  AdminUI.init();
})();
