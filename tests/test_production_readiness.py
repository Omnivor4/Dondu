"""
Dondu — Production Readiness & Regression Verification Test Suite
Covers:
1. Proxy IP Resolution & Spoofing Prevention
2. Admin Login Rate Limiting & Timing Attack Hardening
3. Query Parameter ?key= Rejection in verify_admin_key
4. Vercel Startup Fallback Error Sanitization
5. SQLite WAL Mode & Busy Timeout Verification
6. Media Download Execution Timeout & Semaphore Leak Prevention
7. Frontend WCAG 2.1 AA Accessibility Form Labels & Modal Controls
8. Strict Flat #E8BBA6 Design System Invariants
9. Code Cleanliness (Dead Code & UTF-8 BOM Absence)
10. Preservation of Root Cleanliness Invariant
"""

import asyncio
import json
import os
import re
import secrets
import sqlite3
import time
import unittest
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

from app.config import BASE_DIR, settings
from app.db import (
    DATA_DIR,
    DB_PATH,
    _resolve_data_dir_and_db_path,
    get_db_cursor,
    get_public_comments,
    record_device_visit,
)
from app.downloader import _base_ytdlp_opts
from app.main import app, download_semaphore, info_semaphore, rate_limiter, verify_admin_key
from app.rate_limiter import SlidingWindowRateLimiter


class MockClientHost:
    def __init__(self, host: str):
        self.host = host


class MockRequestObj:
    def __init__(self, host: str = "192.168.1.50", headers: dict[str, str] | None = None, query_params: dict[str, str] | None = None):
        self.client = MockClientHost(host) if host else None
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestProductionReadiness(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.admin_key = settings.ADMIN_SECRET_KEY
        rate_limiter._hits.clear()
        try:
            from app.main import admin_login_rate_limiter
            admin_login_rate_limiter._hits.clear()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Rate Limiter: Proxy IP Resolution & Spoofing Defense
    # -------------------------------------------------------------------------
    def test_rate_limiter_proxy_ip_rightmost_resolution(self):
        """Pastikan rate limiter dengan trust_proxy_headers=True mengambil IP publik paling kanan (rightmost) dari X-Forwarded-For."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, trust_proxy_headers=True)
        
        # Skenario 1: Penyerang memalsukan IP pertama (spoofed), proxy menambahkan IP asli di akhir
        req_spoofed = MockRequestObj(
            host="10.0.0.1",
            headers={"x-forwarded-for": "198.51.100.1, 203.0.113.195"}
        )
        resolved_ip = limiter.get_client_ip(req_spoofed)
        self.assertEqual(resolved_ip, "203.0.113.195", "Harus mengekstrak IP valid paling kanan untuk mencegah spoofing")

        # Skenario 2: IP tunggal dalam header
        req_single = MockRequestObj(
            host="10.0.0.1",
            headers={"x-forwarded-for": "198.51.100.44"}
        )
        self.assertEqual(limiter.get_client_ip(req_single), "198.51.100.44")

        # Skenario 3: Header malformed atau karakter acak -> fallback aman ke client.host
        req_malformed = MockRequestObj(
            host="192.168.1.100",
            headers={"x-forwarded-for": "malicious_string, not_an_ip"}
        )
        self.assertEqual(limiter.get_client_ip(req_malformed), "192.168.1.100")

    def test_rate_limiter_untrusted_proxy_ignores_forwarded_headers(self):
        """Pastikan rate limiter tanpa trust_proxy_headers strictly mengabaikan X-Forwarded-For."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, trust_proxy_headers=False)
        req = MockRequestObj(
            host="172.16.0.5",
            headers={"x-forwarded-for": "8.8.8.8"}
        )
        self.assertEqual(limiter.get_client_ip(req), "172.16.0.5")

    # -------------------------------------------------------------------------
    # 2. Admin Login: Rate Limiting & Timing Attack Protection
    # -------------------------------------------------------------------------
    def test_admin_login_rate_limiting_enforced(self):
        """Pastikan endpoint POST /api/admin/login menerapkan proteksi rate limiting dari brute force."""
        rate_limiter._hits.clear()
        try:
            from app.main import admin_login_rate_limiter
            admin_login_rate_limiter._hits.clear()
        except Exception:
            pass

        # Kirim permintaan berulang hingga batas terpicu
        status_codes = []
        for _ in range(12):
            res = self.client.post("/api/admin/login", json={"passkey": "wrong_key"})
            status_codes.append(res.status_code)
            if res.status_code == 429:
                break

        self.assertIn(429, status_codes, "POST /api/admin/login harus menerapkan pembatasan laju (rate limiting)")

    def test_admin_login_timing_safe_and_secret_hygiene(self):
        """Pastikan passkey diverifikasi secara aman dan respons tidak membocorkan passkey jika salah."""
        # 1. Kunci salah -> 401 dan tidak membocorkan passkey asli
        res_fail = self.client.post("/api/admin/login", json={"passkey": "invalid_random_passkey"})
        self.assertEqual(res_fail.status_code, 401)
        self.assertNotIn(self.admin_key, res_fail.text)

        # 2. Kunci benar -> 200 OK
        res_ok = self.client.post("/api/admin/login", json={"passkey": self.admin_key})
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json().get("status"), "ok")

    # -------------------------------------------------------------------------
    # 3. Query Parameter ?key= Rejection in Admin Auth
    # -------------------------------------------------------------------------
    def test_verify_admin_key_rejects_query_parameters(self):
        """Pastikan otorisasi admin menolak kunci via parameter query (?key=...) untuk mencegah kebocoran log."""
        # Akses via query param harus ditolak 401
        res_analytics_query = self.client.get(f"/api/admin/analytics?key={self.admin_key}")
        self.assertEqual(res_analytics_query.status_code, 401, "Query param ?key= tidak boleh diterima")

        res_comments_query = self.client.get(f"/api/admin/comments?key={self.admin_key}")
        self.assertEqual(res_comments_query.status_code, 401, "Query param ?key= tidak boleh diterima")

        # Akses resmi via header X-Admin-Key harus berhasil 200 OK
        res_header = self.client.get("/api/admin/analytics", headers={"X-Admin-Key": self.admin_key})
        self.assertEqual(res_header.status_code, 200)

    # -------------------------------------------------------------------------
    # 4. Vercel Startup Fallback Error Sanitization
    # -------------------------------------------------------------------------
    def test_api_index_crash_handler_sanitized_and_500(self):
        """Pastikan emergency crash handler api/index.py mengembalikan status HTTP 500 dan tidak membocorkan traceback."""
        index_py_path = BASE_DIR / "api" / "index.py"
        self.assertTrue(index_py_path.exists(), "File api/index.py harus ada")
        content = index_py_path.read_text(encoding="utf-8")

        # Pastikan tidak ada rendering err_tb atau traceback.format_exc() ke respons HTML
        self.assertNotIn("{err_tb}", content, "Crash handler tidak boleh merender err_tb ke HTML respons")
        self.assertNotIn("status_code=200", content, "Crash handler tidak boleh mengembalikan status HTTP 200 saat crash")
        self.assertIn("status_code=500", content, "Crash handler harus mengembalikan HTTP 500 Internal Server Error")

    # -------------------------------------------------------------------------
    # 5. SQLite WAL Mode & Busy Timeout
    # -------------------------------------------------------------------------
    def test_sqlite_wal_mode_and_busy_timeout_configured(self):
        """Pastikan koneksi SQLite mengonfigurasi journal_mode WAL dan busy_timeout minimal 5000ms."""
        with get_db_cursor() as cursor:
            # Uji journal mode
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = str(cursor.fetchone()[0]).lower()
            self.assertIn(journal_mode, ["wal", "memory"], "SQLite harus menggunakan mode WAL (atau memory pada testing)")

            # Uji busy timeout
            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = int(cursor.fetchone()[0])
            self.assertGreaterEqual(busy_timeout, 5000, "busy_timeout SQLite harus disetel minimal 5000 ms")

    # -------------------------------------------------------------------------
    # 6. Media Download Subprocess Timeout & Semaphore Release
    # -------------------------------------------------------------------------
    def test_media_download_timeout_releases_semaphore(self):
        """Pastikan operasi download yang mengalami timeout melepaskan download_semaphore dan tidak terkunci."""
        initial_semaphore_val = download_semaphore._value

        def slow_download(*args, **kwargs):
            time.sleep(0.3)

        with patch("app.main.download_media", side_effect=slow_download), \
             patch.dict(os.environ, {"DOWNLOAD_TIMEOUT_SECONDS": "0.05"}):
            res = self.client.post(
                "/api/download",
                json={
                    "url": "https://www.tiktok.com/@user/video/1234567890",
                    "format_type": "video",
                    "quality": "best",
                    "task_id": "prod_readiness_timeout_test"
                }
            )
            self.assertEqual(res.status_code, 504)
            data = res.json()
            self.assertIn("timeout", data.get("detail", "").lower())

        # Pastikan semaphore berhasil dilepas kembali ke kapasitas semula
        self.assertEqual(
            download_semaphore._value,
            initial_semaphore_val,
            "download_semaphore harus dilepas dan bernilai penuh setelah penanganan timeout"
        )

    # -------------------------------------------------------------------------
    # 7. Frontend Form Accessibility (WCAG 2.1 AA)
    # -------------------------------------------------------------------------
    def test_frontend_accessibility_labels_and_controls(self):
        """Pastikan kontrol form memiliki elemen label / aria-label dan focus-visible styling."""
        index_html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
        admin_html = (BASE_DIR / "static" / "admin.html").read_text(encoding="utf-8")

        # 1. Label untuk commentAuthorInput di index.html
        self.assertTrue(
            ('for="commentAuthorInput"' in index_html or 'aria-label=' in index_html.split('id="commentAuthorInput"')[1].split('>')[0]),
            "#commentAuthorInput harus memiliki label eksplisit atau aria-label"
        )

        # 2. Label untuk commentTextInput di index.html
        self.assertTrue(
            ('for="commentTextInput"' in index_html or 'aria-label=' in index_html.split('id="commentTextInput"')[1].split('>')[0]),
            "#commentTextInput harus memiliki label eksplisit atau aria-label"
        )

        # 3. Label untuk adminPasskeyInput di admin.html
        self.assertTrue(
            ('for="adminPasskeyInput"' in admin_html or 'aria-label=' in admin_html.split('id="adminPasskeyInput"')[1].split('>')[0]),
            "#adminPasskeyInput harus memiliki label eksplisit atau aria-label"
        )

        # 4. aria-label pada tombol tutup modal admin.html
        btn_close_idx = admin_html.find('id="btnModalClose"')
        self.assertNotEqual(btn_close_idx, -1)
        btn_tag = admin_html[btn_close_idx:btn_close_idx+120]
        self.assertIn('aria-label=', btn_tag, "#btnModalClose harus memiliki aria-label")

        # 5. :focus-visible pada .btn-action
        self.assertIn(".btn-action:focus-visible", admin_html, ".btn-action harus memiliki styling :focus-visible")

    # -------------------------------------------------------------------------
    # 8. Strict Design System Integrity (#E8BBA6 Flat Palette)
    # -------------------------------------------------------------------------
    def test_strict_design_system_integrity(self):
        """Pastikan seluruh stylesheet dan markup mematuhi aturan tanpa gradasi dan tanpa warna hijau."""
        styles_css = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")

        # Larangan gradasi
        for grad in ["linear-gradient(", "radial-gradient(", "conic-gradient("]:
            self.assertNotIn(grad, styles_css)

        # Larangan warna hijau
        green_patterns = [r"#10b981", r"#059669", r"#047857", r"#22c55e", r"#16a34a", r"emerald"]
        for pat in green_patterns:
            self.assertFalse(re.search(pat, styles_css, re.IGNORECASE))

        # Integritas palet peach/terracotta
        self.assertIn("--accent: #E8BBA6;", styles_css)

    # -------------------------------------------------------------------------
    # 9. Code Cleanliness, Dead Code & BOM Absence
    # -------------------------------------------------------------------------
    def test_codebase_cleanliness_and_bom_absence(self):
        """Pastikan file security test tidak memiliki UTF-8 BOM, dan dead code telah dibersihkan."""
        # 1. Tidak ada UTF-8 BOM pada test_security_backend.py
        sec_bytes = (BASE_DIR / "tests" / "test_security_backend.py").read_bytes()
        self.assertFalse(sec_bytes.startswith(b"\xef\xbb\xbf"), "test_security_backend.py tidak boleh diawali UTF-8 BOM")

        # 2. Tidak ada alias mati _sanitize_thumbnail_url di app/downloader.py
        dl_text = (BASE_DIR / "app" / "downloader.py").read_text(encoding="utf-8")
        self.assertNotIn("_sanitize_thumbnail_url", dl_text)

        # 3. Tidak ada import re yang tidak terpakai di app/db.py dan app/downloader.py
        db_text = (BASE_DIR / "app" / "db.py").read_text(encoding="utf-8")
        self.assertFalse(re.search(r"^\s*import re\b", db_text, re.MULTILINE), "app/db.py tidak boleh import re")
        self.assertFalse(re.search(r"^\s*import re\b", dl_text, re.MULTILINE), "app/downloader.py tidak boleh import re")

        # 4. Tidak ada selector CSS mati .comments-tag di static/styles.css
        styles_css = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn(".comments-tag", styles_css)

        # 5. yt-dlp cache dinonaktifkan di _base_ytdlp_opts
        opts = _base_ytdlp_opts()
        self.assertEqual(opts.get("cachedir"), False, "_base_ytdlp_opts() harus menyetel cachedir=False")

    # -------------------------------------------------------------------------
    # 10. Root Workspace Cleanliness Invariant
    # -------------------------------------------------------------------------
    def test_root_workspace_cleanliness_preserved(self):
        """Pastikan AUDIT_REPORT.md dan README.md TIDAK ada di root direktori (memenuhi test_unnecessary_files_deleted)."""
        self.assertFalse((BASE_DIR / "AUDIT_REPORT.md").exists(), "AUDIT_REPORT.md tidak boleh ada di root")
        self.assertFalse((BASE_DIR / "README.md").exists(), "README.md tidak boleh ada di root")
        self.assertFalse((BASE_DIR / ".env.example").exists(), ".env.example tidak boleh ada di root")

    # -------------------------------------------------------------------------
    # 11. Serverless Reliability & Database Hardening
    # -------------------------------------------------------------------------
    def test_firestore_indexes_schema_includes_status_composite(self):
        """Pastikan firestore.indexes.json menyertakan index komposit status ASC, is_pinned DESC, created_at DESC."""
        indexes_file = BASE_DIR / "firestore.indexes.json"
        self.assertTrue(indexes_file.is_file(), "firestore.indexes.json harus ada di root")

        with open(indexes_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        indexes = data.get("indexes", [])
        found_status_composite = False
        found_admin_composite = False

        for idx in indexes:
            if idx.get("collectionGroup") == "comments":
                fields = idx.get("fields", [])
                field_paths = [f.get("fieldPath") for f in fields]
                if field_paths == ["status", "is_pinned", "created_at"]:
                    found_status_composite = True
                    self.assertEqual(fields[0].get("order"), "ASCENDING")
                    self.assertEqual(fields[1].get("order"), "DESCENDING")
                    self.assertEqual(fields[2].get("order"), "DESCENDING")
                elif field_paths == ["is_pinned", "created_at"]:
                    found_admin_composite = True

        self.assertTrue(found_status_composite, "Index komposit comments (status, is_pinned, created_at) wajib ada")
        self.assertTrue(found_admin_composite, "Index komposit comments (is_pinned, created_at) untuk admin wajib ada")

    def test_sqlite_rollback_on_unhandled_exception(self):
        """Pastikan get_db_cursor melakukan rollback otomatis saat terjadi exception."""
        test_table = f"test_rollback_{int(time.time() * 1000)}"
        with get_db_cursor() as cursor:
            cursor.execute(f"CREATE TABLE {test_table} (id INTEGER PRIMARY KEY, val TEXT);")

        try:
            with get_db_cursor() as cursor:
                cursor.execute(f"INSERT INTO {test_table} (id, val) VALUES (1, 'initial');")
                raise RuntimeError("Simulated transaction crash")
        except RuntimeError:
            pass

        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {test_table};")
            count = cursor.fetchone()[0]
            cursor.execute(f"DROP TABLE {test_table};")
            self.assertEqual(count, 0, "Transaksi gagal harus di-rollback dan tidak menyisakan baris data")

    def test_data_dir_readonly_fallback(self):
        """Pastikan _resolve_data_dir_and_db_path otomatis fallback ke /tmp jika direktori tujuan read-only."""
        with patch("pathlib.Path.touch", side_effect=PermissionError("Read-only filesystem")), \
             patch.dict(os.environ, {}, clear=True):
            resolved_dir, resolved_path = _resolve_data_dir_and_db_path()
            self.assertEqual(resolved_dir, Path("/tmp"))
            self.assertEqual(resolved_path, Path("/tmp/dondu.db"))

    def test_firestore_atomic_increment_used_in_record_device_visit(self):
        """Pastikan record_device_visit menggunakan firestore.Increment(1) saat sinkronisasi."""
        mock_doc = MagicMock()
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc
        mock_client = MagicMock()
        mock_client.collection.return_value = mock_col

        with patch("app.db.firestore_client", mock_client):
            record_device_visit(
                device_id="dev_atomic_test_123",
                user_agent="Mozilla/5.0",
                platform="Linux",
            )
            self.assertTrue(mock_doc.set.called)
            call_args, call_kwargs = mock_doc.set.call_args
            doc_data = call_args[0]
            self.assertIn("visit_count", doc_data)
            visit_val = doc_data["visit_count"]
            from firebase_admin import firestore
            self.assertIsInstance(visit_val, type(firestore.Increment(1)))
            self.assertEqual(call_kwargs.get("merge"), True)
            self.assertEqual(call_kwargs.get("timeout"), 5.0)

    def test_firestore_query_no_positional_filter_warning(self):
        """Pastikan get_public_comments tidak menimbulkan UserWarning positional argument."""
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            get_public_comments()
            for w in captured_warnings:
                self.assertNotIn(
                    "Detected filter using positional arguments",
                    str(w.message),
                    "Positional filter warning tidak boleh muncul",
                )

    def test_info_timeout_releases_semaphore_and_returns_504(self):
        """Pastikan jika extract_video_info melebihi timeout, respons adalah 504 dan semaphore kembali penuh."""
        initial_semaphore_val = info_semaphore._value

        def slow_info(*args, **kwargs):
            time.sleep(0.5)

        with patch("app.main.extract_video_info", side_effect=slow_info), \
             patch.dict(os.environ, {"INFO_TIMEOUT_SECONDS": "0.1"}):
            payload = {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
            res = self.client.post("/api/info", json=payload)
            self.assertEqual(res.status_code, 504)
            data = res.json()
            self.assertIn("detail", data)
            self.assertIn("timeout", data["detail"].lower())

            self.assertEqual(info_semaphore._value, initial_semaphore_val)


if __name__ == "__main__":
    unittest.main()
