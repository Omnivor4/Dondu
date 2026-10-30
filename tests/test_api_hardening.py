import asyncio
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.downloader import DownloaderUserError, download_media, extract_video_info
from app.main import app, download_semaphore, info_semaphore, progress_rate_limiter, rate_limiter
from app.validators import URLValidationError


class TestApiHardening(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        rate_limiter._hits.clear()
        progress_rate_limiter._hits.clear()

    def test_security_headers_on_root_and_health(self):
        """Pastikan security headers terpasang di semua respons (termasuk / dan /health)."""
        expected_csp = (
            "default-src 'self'; img-src 'self' https: http: data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )

        for path in ["/", "/health"]:
            response = self.client.get(path)
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
            self.assertEqual(
                response.headers.get("Permissions-Policy"),
                "camera=(), microphone=(), geolocation=()",
            )
            self.assertEqual(response.headers.get("Content-Security-Policy"), expected_csp)

    def test_health_endpoint_no_version_leak(self):
        """Pastikan /health tidak membocorkan yt_dlp_version dan mengembalikan status ok."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("app"), "Forte")
        self.assertIn("version", data)
        self.assertIn("ffmpeg_installed", data)
        self.assertIn("limits", data)
        # yt_dlp_version harus dihapus untuk mencegah fingerprinting versi library publik
        self.assertNotIn("yt_dlp_version", data)

    def test_docs_and_openapi_disabled_by_default(self):
        """Pastikan /docs dan /openapi.json mengembalikan 404 saat ENABLE_DOCS=false."""
        self.assertFalse(settings.ENABLE_DOCS)
        docs_res = self.client.get("/docs")
        self.assertEqual(docs_res.status_code, 404)

        openapi_res = self.client.get("/openapi.json")
        self.assertEqual(openapi_res.status_code, 404)

    def test_progress_endpoint_rejects_invalid_task_id(self):
        """Pastikan /api/progress/{task_id} menolak karakter task_id tidak valid dengan 400."""
        from urllib.parse import quote

        invalid_ids = [
            "task;drop",
            "task<script>",
            "task id",
            "task$#@",
            "task.id",
            "task!id",
            "a" * 65,
        ]
        for task_id in invalid_ids:
            quoted_id = quote(task_id, safe="")
            response = self.client.get(f"/api/progress/{quoted_id}")
            self.assertEqual(
                response.status_code,
                400,
                f"task_id '{task_id}' ({quoted_id}) seharusnya ditolak dengan status 400",
            )
            data = response.json()
            self.assertIn("detail", data)

    def test_progress_endpoint_valid_task_id(self):
        """Pastikan /api/progress/{task_id} dengan ID valid mengembalikan 200."""
        response = self.client.get("/api/progress/valid-task_123")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["task_id"], "valid-task_123")
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["percent"], 0.0)

    def test_progress_rate_limiting(self):
        """Pastikan /api/progress/{task_id} dibatasi oleh progress_rate_limiter."""
        from collections import deque
        import time

        now = time.monotonic()
        progress_rate_limiter._hits["testclient"] = deque([now] * 120)
        response = self.client.get("/api/progress/rate-limit-test")
        self.assertEqual(response.status_code, 429)

    def test_info_endpoint_rejects_disallowed_domains(self):
        """Pastikan /api/info menolak domain tidak didukung atau berbahaya dengan 400."""
        bad_payloads = [
            {"url": "https://evil.com/video"},
            {"url": "http://127.0.0.1/video"},
            {"url": "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ"},
            {"url": "https://youtube.com:8080/watch?v=dQw4w9WgXcQ"},
            {"url": "https://attacker.example.org/exploit"},
        ]
        for payload in bad_payloads:
            response = self.client.post("/api/info", json=payload)
            self.assertEqual(
                response.status_code,
                400,
                f"URL '{payload['url']}' seharusnya ditolak dengan 400",
            )
            data = response.json()
            self.assertIn("detail", data)

    def test_info_semaphore_timeout_returns_503(self):
        """Pastikan timeout saat mengakuisisi info_semaphore menghasilkan respons 503."""
        with patch.object(info_semaphore, "acquire", side_effect=asyncio.TimeoutError):
            response = self.client.post(
                "/api/info",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertIn("Server sedang sibuk memproses banyak permintaan", data["detail"])

    def test_download_endpoint_rejects_invalid_task_id(self):
        """Pastikan /api/download menolak task_id yang tidak valid."""
        payload = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format_type": "video",
            "quality": "best",
            "task_id": "invalid;task!id",
        }
        response = self.client.post("/api/download", json=payload)
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("detail", data)

    def test_download_semaphore_timeout_returns_503(self):
        """Pastikan timeout saat mengakuisisi download_semaphore menghasilkan respons 503."""
        with patch.object(download_semaphore, "acquire", side_effect=asyncio.TimeoutError):
            payload = {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "format_type": "video",
                "quality": "best",
                "task_id": "valid-download-task",
            }
            response = self.client.post("/api/download", json=payload)
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertIn("Server sedang memproses batas maksimum unduhan bersamaan", data["detail"])

    def test_unlimited_defaults_in_config(self):
        """Pastikan konfigurasi default MAX_DURATION_MINUTES dan MAX_FILE_SIZE_MB adalah 0 (unlimited)."""
        self.assertEqual(settings.MAX_DURATION_MINUTES, 0)
        self.assertEqual(settings.MAX_DURATION_SECONDS, 0)
        self.assertEqual(settings.MAX_FILE_SIZE_MB, 0)
        self.assertEqual(settings.MAX_FILE_SIZE_BYTES, 0)

    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_unlimited_duration_allows_long_videos(self, mock_ydl_cls):
        """Saat MAX_DURATION_SECONDS == 0, video berdurasi sangat panjang tidak ditolak."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "title": "Super Long Stream",
            "duration": 9999999,  # Durasi sangat panjang
            "uploader": "Long Channel",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "formats": [],
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        res = extract_video_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(res.duration, 9999999)

    @patch("app.downloader.is_ffmpeg_available", return_value=True)
    @patch("app.downloader.yt_dlp.YoutubeDL")
    def test_skip_audio_thumbnail_retry_on_validation_error(self, mock_ydl_cls, mock_ffmpeg):
        """Pastikan download_media tidak mengulangi konversi jika error pertama adalah kesalahan validasi."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = URLValidationError("Domain tidak diizinkan")
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        with self.assertRaises(DownloaderUserError) as cm:
            download_media("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "audio", "192")

        # extract_info hanya boleh dipanggil 1 kali (tidak ada retry!)
        self.assertEqual(mock_ydl.extract_info.call_count, 1)


if __name__ == "__main__":
    unittest.main()
