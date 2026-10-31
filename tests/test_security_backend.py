import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.downloader import (
    DownloaderUserError,
    ProgressTracker,
    _base_ytdlp_opts,
    download_media,
    extract_video_info,
    map_ytdlp_error,
    sanitize_thumbnail_url,
)
from app.rate_limiter import SlidingWindowRateLimiter
from app.validators import URLValidationError


class MockClient:
    def __init__(self, host: str):
        self.host = host


class MockRequest:
    def __init__(self, host: str = "127.0.0.1", headers: dict[str, str] | None = None):
        self.client = MockClient(host) if host else None
        self.headers = headers or {}


class TestSecurityBackend(unittest.TestCase):
    # -------------------------------------------------------------------------
    # 1. Rate Limiter: Proxy Header Spoofing & IP Sanitization
    # -------------------------------------------------------------------------
    def test_rate_limiter_ignores_spoofed_proxy_headers_by_default(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, trust_proxy_headers=False)
        req = MockRequest(
            host="192.168.1.50",
            headers={
                "x-forwarded-for": "203.0.113.195, 70.41.3.18",
                "x-real-ip": "198.51.100.1",
            },
        )
        # Must return the direct TCP client host, completely ignoring proxy headers
        self.assertEqual(limiter.get_client_ip(req), "192.168.1.50")

    def test_rate_limiter_honors_proxy_headers_when_configured(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, trust_proxy_headers=True)

        # X-Forwarded-For with multiple IPs: takes the rightmost (proxy-appended) client IP
        req_xff = MockRequest(
            host="10.0.0.1",
            headers={"x-forwarded-for": "203.0.113.195, 70.41.3.18"},
        )
        self.assertEqual(limiter.get_client_ip(req_xff), "70.41.3.18")

        # X-Real-IP fallback when X-Forwarded-For is not present
        req_xreal = MockRequest(
            host="10.0.0.1",
            headers={"x-real-ip": "198.51.100.22"},
        )
        self.assertEqual(limiter.get_client_ip(req_xreal), "198.51.100.22")

        # Fallback to direct client host when no proxy headers exist
        req_direct = MockRequest(host="10.0.0.1", headers={})
        self.assertEqual(limiter.get_client_ip(req_direct), "10.0.0.1")

    def test_rate_limiter_ip_sanitization(self):
        limiter = SlidingWindowRateLimiter(trust_proxy_headers=True)

        # Strips whitespace
        req_spaces = MockRequest(headers={"x-forwarded-for": "  203.0.113.50  "})
        self.assertEqual(limiter.get_client_ip(req_spaces), "203.0.113.50")

        # Non-IP string rejected and falls back to socket client host
        oversized = "a" * 100
        req_oversized = MockRequest(headers={"x-forwarded-for": oversized})
        result = limiter.get_client_ip(req_oversized)
        self.assertEqual(result, "127.0.0.1")

        # Empty / None client host falls back to "unknown"
        req_empty = MockRequest(host="", headers={})
        self.assertEqual(limiter.get_client_ip(req_empty), "unknown")

    def test_rate_limiter_extracts_rightmost_ip_under_proxy_spoofing(self):
        """Pastikan rate limiter selalu mengambil IP paling kanan untuk mencegah spoofing X-Forwarded-For."""
        limiter = SlidingWindowRateLimiter(trust_proxy_headers=True)
        req = MockRequest(
            host="10.0.0.1",
            headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8, 198.51.100.99"},
        )
        self.assertEqual(limiter.get_client_ip(req), "198.51.100.99")

    def test_rate_limiter_rejects_malformed_ip_strings(self):
        """Pastikan string bukan IP valid ditolak dan fallback ke host TCP client."""
        limiter = SlidingWindowRateLimiter(trust_proxy_headers=True)
        req = MockRequest(
            host="192.168.1.10",
            headers={"x-forwarded-for": "invalid-ip-payload<script>"},
        )
        self.assertEqual(limiter.get_client_ip(req), "192.168.1.10")

    def test_rate_limiter_blocks_spoofing_bypass_attempts(self):
        # When trust_proxy_headers=False, varying X-Forwarded-For should NOT bypass the limit
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60, trust_proxy_headers=False)
        req1 = MockRequest(host="1.2.3.4", headers={"x-forwarded-for": "10.0.0.1"})
        req2 = MockRequest(host="1.2.3.4", headers={"x-forwarded-for": "10.0.0.2"})
        req3 = MockRequest(host="1.2.3.4", headers={"x-forwarded-for": "10.0.0.3"})

        limiter.check(req1)
        limiter.check(req2)
        with self.assertRaises(HTTPException) as ctx:
            limiter.check(req3)
        self.assertEqual(ctx.exception.status_code, 429)

    # -------------------------------------------------------------------------
    # 2. Rate Limiter Memory Bounding & Eviction
    # -------------------------------------------------------------------------
    def test_rate_limiter_evicts_oldest_ip_at_capacity(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, max_tracked_ips=3)
        req_ips = ["192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4"]

        for ip in req_ips[:3]:
            limiter.check(MockRequest(host=ip))

        self.assertEqual(len(limiter._hits), 3)
        self.assertIn("192.168.1.1", limiter._hits)
        self.assertIn("192.168.1.2", limiter._hits)
        self.assertIn("192.168.1.3", limiter._hits)

        # 4th unique IP arrives: oldest ("192.168.1.1") must be evicted
        limiter.check(MockRequest(host=req_ips[3]))
        self.assertEqual(len(limiter._hits), 3)
        self.assertNotIn("192.168.1.1", limiter._hits)
        self.assertIn("192.168.1.2", limiter._hits)
        self.assertIn("192.168.1.3", limiter._hits)
        self.assertIn("192.168.1.4", limiter._hits)

        # Existing IP does not cause eviction
        limiter.check(MockRequest(host="192.168.1.2"))
        self.assertEqual(len(limiter._hits), 3)

    # -------------------------------------------------------------------------
    # 3. Progress Tracker Bounded Memory & Eviction
    # -------------------------------------------------------------------------
    def test_progress_tracker_evicts_oldest_entry_at_capacity(self):
        tracker = ProgressTracker(max_entries=3)
        tracker.update("task_1", "downloading", 10.0, "Progress 1")
        tracker.update("task_2", "downloading", 20.0, "Progress 2")
        tracker.update("task_3", "downloading", 30.0, "Progress 3")

        self.assertEqual(len(tracker._store), 3)
        self.assertEqual(tracker.get("task_1").status, "downloading")

        # 4th task arrives: task_1 must be evicted
        tracker.update("task_4", "downloading", 40.0, "Progress 4")
        self.assertEqual(len(tracker._store), 3)
        self.assertNotIn("task_1", tracker._store)
        self.assertIn("task_2", tracker._store)
        self.assertIn("task_3", tracker._store)
        self.assertIn("task_4", tracker._store)

        # Getting evicted task returns pending default
        self.assertEqual(tracker.get("task_1").status, "pending")

        # Updating existing task does not evict
        tracker.update("task_2", "completed", 100.0, "Done")
        self.assertEqual(len(tracker._store), 3)

    # -------------------------------------------------------------------------
    # 4. Thumbnail URL Sanitization
    # -------------------------------------------------------------------------
    def test_sanitize_thumbnail_url(self):
        # Allowed URLs
        good_urls = [
            "https://i.ytimg.com/vi/abc123xyz/hqdefault.jpg",
            "http://example.com/images/thumb.jpg",
            " https://i.ytimg.com/vi/abc123xyz/hqdefault.jpg ",
            "https://p16-va.tiktokcdn.com/obj/tos-maliva-p/cover.jpeg?x-expires=123",
        ]
        for url in good_urls:
            with self.subTest(url=url):
                res = sanitize_thumbnail_url(url)
                self.assertIsNotNone(res)
                self.assertEqual(res, url.strip())

        # Disallowed / Malicious URLs
        bad_urls = [
            "javascript:alert(1)",
            "javascript://alert(1)",
            "data:text/html,<script>alert('xss')</script>",
            "data:image/svg+xml;base64,PHN2Zy...",
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://files.example.com/pic.jpg",
            "https://example.com/pic with spaces.jpg",
            "https://example.com/pic\x00null.jpg",
            "https://example.com/pic\r\ninjection.jpg",
            "https://example.com/" + "a" * 2050,  # exceeds 2048 chars
            "",
            "   ",
            None,
            12345,
            ["https://example.com/pic.jpg"],
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                self.assertIsNone(sanitize_thumbnail_url(url))

    # -------------------------------------------------------------------------
    # 5. Base yt-dlp Options: Protocol & Download Cap
    # -------------------------------------------------------------------------
    def test_base_ytdlp_opts_security_restrictions(self):
        opts = _base_ytdlp_opts()
        self.assertEqual(opts.get("allowed_protocols"), ["http", "https"])
        self.assertEqual(opts.get("max_downloads"), 1)

    # -------------------------------------------------------------------------
    # 6. map_ytdlp_error handles URLValidationError as 400
    # -------------------------------------------------------------------------
    def test_map_ytdlp_error_maps_url_validation_error(self):
        exc = URLValidationError("Domain 'evil.com' tidak didukung.")
        user_err = map_ytdlp_error(exc)
        self.assertIsInstance(user_err, DownloaderUserError)
        self.assertEqual(user_err.status_code, 400)
        self.assertIn("evil.com", user_err.message)

    # -------------------------------------------------------------------------
    # 7. SSRF / Post-Redirect Post-Extraction Guard
    # -------------------------------------------------------------------------
    @patch("yt_dlp.YoutubeDL")
    def test_extract_video_info_rejects_unauthorized_redirect(self, mock_ydl_cls):
        # Input is a valid shortlink (e.g. t.co for X), but redirect resolves to unauthorized domain
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "webpage_url": "https://evil.example.com/video.mp4",
            "title": "Malicious Video",
            "duration": 30,
        }

        with self.assertRaises(URLValidationError) as ctx:
            extract_video_info("https://t.co/xyz123")

        self.assertIn("evil.example.com", str(ctx.exception))
        self.assertIn("tidak didukung", str(ctx.exception).lower())

    @patch("yt_dlp.YoutubeDL")
    def test_extract_video_info_rejects_internal_ip_redirect(self, mock_ydl_cls):
        # Shortlink redirecting to internal service (SSRF)
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        # Test internal loopback IP on standard HTTP port
        mock_ydl.extract_info.return_value = {
            "webpage_url": "http://127.0.0.1/admin",
            "title": "Internal Service",
            "duration": 30,
        }
        with self.assertRaises(URLValidationError) as ctx:
            extract_video_info("https://t.co/internal123")
        self.assertIn("internal atau lokal", str(ctx.exception).lower())

        # Test internal loopback IP on non-standard port
        mock_ydl.extract_info.return_value = {
            "webpage_url": "http://127.0.0.1:8000/admin",
            "title": "Internal Service Port 8000",
            "duration": 30,
        }
        with self.assertRaises(URLValidationError) as ctx:
            extract_video_info("https://t.co/internal123")
        self.assertIn("port pada tautan tidak diizinkan", str(ctx.exception).lower())

    @patch("yt_dlp.YoutubeDL")
    def test_extract_video_info_checks_original_url_fallback(self, mock_ydl_cls):
        # Fallback to original_url if webpage_url is absent
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "original_url": "https://attacker.com/exploit.mp4",
            "title": "Exploit",
            "duration": 30,
        }

        with self.assertRaises(URLValidationError) as ctx:
            extract_video_info("https://t.co/exploit123")

        self.assertIn("attacker.com", str(ctx.exception))

    @patch("app.downloader.is_ffmpeg_available", return_value=True)
    @patch("yt_dlp.YoutubeDL")
    def test_download_media_rejects_unauthorized_redirect_before_download(
        self, mock_ydl_cls, mock_ffmpeg
    ):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "webpage_url": "https://evil.example.com/payload.mp4",
            "title": "Malicious Payload",
            "duration": 30,
        }

        with self.assertRaises(DownloaderUserError) as ctx:
            download_media("https://t.co/redirect123", "video", "best", "test_task_1")

        # Must return 400 Bad Request
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("evil.example.com", ctx.exception.message)
        # CRITICAL: ydl.download must NEVER be called when redirect target is rejected
        mock_ydl.download.assert_not_called()

    @patch("app.downloader.is_ffmpeg_available", return_value=True)
    @patch("yt_dlp.YoutubeDL")
    def test_download_media_rejects_internal_ip_redirect_before_download(
        self, mock_ydl_cls, mock_ffmpeg
    ):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "webpage_url": "http://169.254.169.254/latest/meta-data/",
            "title": "AWS Metadata SSRF",
            "duration": 30,
        }

        with self.assertRaises(DownloaderUserError) as ctx:
            download_media("https://t.co/metadata123", "video", "best", "test_task_2")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("internal atau lokal", ctx.exception.message.lower())
        mock_ydl.download.assert_not_called()

    @patch("yt_dlp.YoutubeDL")
    def test_extract_video_info_sanitizes_thumbnail(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "webpage_url": "https://x.com/jack/status/20",
            "title": "Jack Post",
            "duration": 30,
            "thumbnail": "javascript:alert(1)",
        }

        info = extract_video_info("https://t.co/abc123xyz")
        # Malicious thumbnail URL must be sanitized to None
        self.assertIsNone(info.thumbnail)


if __name__ == "__main__":
    unittest.main()
