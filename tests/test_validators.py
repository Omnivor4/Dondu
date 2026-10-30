import socket
import unittest
from unittest.mock import patch
from pydantic import ValidationError

from app.schemas import DownloadRequest
from app.validators import (
    URLValidationError,
    build_content_disposition,
    is_forbidden_host_or_ip,
    sanitize_filename,
    validate_and_identify_url,
    validate_task_id,
)


class TestValidators(unittest.TestCase):
    # -------------------------------------------------------------------------
    # 1. Valid URLs for all 5 platforms
    # -------------------------------------------------------------------------
    def test_valid_urls_all_platforms(self):
        cases = [
            ("https://www.tiktok.com/@creator/video/1234567890123456789", "TikTok"),
            ("https://vm.tiktok.com/ZMxxxxxx/", "TikTok"),
            ("https://vt.tiktok.com/ZSxxxxxx/", "TikTok"),
            ("https://www.instagram.com/p/C-123456789/", "Instagram"),
            ("https://www.instagram.com/reel/C-123456789/", "Instagram"),
            ("https://instagr.am/p/C-123456789/", "Instagram"),
            ("https://ddinstagram.com/p/C-123456789/", "Instagram"),
            ("https://www.facebook.com/watch/?v=123456789", "Facebook"),
            ("https://fb.watch/abcdef123/", "Facebook"),
            ("https://fb.com/watch/?v=123456789", "Facebook"),
            ("https://x.com/jack/status/20", "X"),
            ("https://twitter.com/jack/status/20", "X"),
            ("https://fxtwitter.com/jack/status/20", "X"),
            ("https://vxtwitter.com/jack/status/20", "X"),
            ("https://t.co/abc123xyz", "X"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
            ("https://youtu.be/dQw4w9WgXcQ", "YouTube"),
            ("https://youtube-nocookie.com/embed/dQw4w9WgXcQ", "YouTube"),
        ]
        for url, expected_platform in cases:
            with self.subTest(url=url, platform=expected_platform):
                cleaned_url, platform = validate_and_identify_url(url)
                self.assertEqual(platform, expected_platform)
                self.assertEqual(cleaned_url, url)

    # -------------------------------------------------------------------------
    # 2. Rejection of unsupported domains and spoofed domains
    # -------------------------------------------------------------------------
    def test_rejection_of_unsupported_domains(self):
        unsupported = [
            "https://vimeo.com/12345678",
            "https://evil-youtube.com/watch?v=123",
            "https://youtube.com.attacker.com/watch?v=123",
            "https://tiktok.com.phishing.io/@user/video/1",
            "https://notfacebook.com/video",
            "https://dailymotion.com/video/x7xxxx",
        ]
        for url in unsupported:
            with self.subTest(url=url):
                with self.assertRaises(URLValidationError) as ctx:
                    validate_and_identify_url(url)
                self.assertIn("tidak didukung", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # 3. Rejection of URLs with embedded credentials
    # -------------------------------------------------------------------------
    def test_rejection_of_urls_with_embedded_credentials(self):
        creds_urls = [
            "https://user:pass@www.youtube.com/watch?v=123",
            "https://admin@www.tiktok.com/@user/video/123",
            "https://:secret@x.com/user/status/123",
        ]
        for url in creds_urls:
            with self.subTest(url=url):
                with self.assertRaises(URLValidationError) as ctx:
                    validate_and_identify_url(url)
                self.assertIn("kredensial autentikasi", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 4. Port checks: non-standard rejected, standard (80, 443, None) accepted
    # -------------------------------------------------------------------------
    def test_rejection_of_non_standard_ports(self):
        bad_port_urls = [
            "https://www.youtube.com:8080/watch?v=123",
            "https://x.com:8443/user/status/1",
            "http://www.instagram.com:3000/p/123/",
            "https://www.facebook.com:22/watch/?v=1",
        ]
        for url in bad_port_urls:
            with self.subTest(url=url):
                with self.assertRaises(URLValidationError) as ctx:
                    validate_and_identify_url(url)
                self.assertIn("Port pada tautan tidak diizinkan", str(ctx.exception))

    def test_acceptance_of_standard_ports(self):
        good_port_urls = [
            ("http://www.youtube.com:80/watch?v=dQw4w9WgXcQ", "YouTube"),
            ("https://www.youtube.com:443/watch?v=dQw4w9WgXcQ", "YouTube"),
        ]
        for url, expected_platform in good_port_urls:
            with self.subTest(url=url):
                cleaned_url, platform = validate_and_identify_url(url)
                self.assertEqual(platform, expected_platform)

    # -------------------------------------------------------------------------
    # 5. SSRF protection: private/loopback IPs & is_forbidden_host_or_ip
    # -------------------------------------------------------------------------
    def test_is_forbidden_host_or_ip_hostnames(self):
        # Forbidden hostnames
        self.assertTrue(is_forbidden_host_or_ip("localhost"))
        self.assertTrue(is_forbidden_host_or_ip("my-pc.local"))
        self.assertTrue(is_forbidden_host_or_ip("metadata.google.internal"))
        self.assertTrue(is_forbidden_host_or_ip("1.0.0.127.in-addr.arpa"))
        self.assertTrue(is_forbidden_host_or_ip("sub.localhost"))
        self.assertTrue(is_forbidden_host_or_ip(""))

        # Safe hostnames
        self.assertFalse(is_forbidden_host_or_ip("youtube.com"))
        self.assertFalse(is_forbidden_host_or_ip("www.tiktok.com"))
        self.assertFalse(is_forbidden_host_or_ip("x.com"))

    def test_is_forbidden_host_or_ip_literal_ips(self):
        # Loopback IPv4 & IPv6
        self.assertTrue(is_forbidden_host_or_ip("127.0.0.1"))
        self.assertTrue(is_forbidden_host_or_ip("127.1.2.3"))
        self.assertTrue(is_forbidden_host_or_ip("::1"))
        self.assertTrue(is_forbidden_host_or_ip("[::1]"))

        # Private IPv4
        self.assertTrue(is_forbidden_host_or_ip("10.0.0.1"))
        self.assertTrue(is_forbidden_host_or_ip("172.16.0.1"))
        self.assertTrue(is_forbidden_host_or_ip("192.168.1.1"))

        # Link-local & cloud metadata
        self.assertTrue(is_forbidden_host_or_ip("169.254.169.254"))
        self.assertTrue(is_forbidden_host_or_ip("fe80::1"))

        # Multicast & Unspecified
        self.assertTrue(is_forbidden_host_or_ip("224.0.0.1"))
        self.assertTrue(is_forbidden_host_or_ip("0.0.0.0"))

        # IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1 or ::ffff:192.168.1.1)
        self.assertTrue(is_forbidden_host_or_ip("::ffff:127.0.0.1"))
        self.assertTrue(is_forbidden_host_or_ip("[::ffff:127.0.0.1]"))
        self.assertTrue(is_forbidden_host_or_ip("::ffff:192.168.1.1"))
        self.assertTrue(is_forbidden_host_or_ip("::ffff:169.254.169.254"))

        # Safe public IPs
        self.assertFalse(is_forbidden_host_or_ip("8.8.8.8"))
        self.assertFalse(is_forbidden_host_or_ip("1.1.1.1"))
        self.assertFalse(is_forbidden_host_or_ip("::ffff:8.8.8.8"))

    def test_is_forbidden_host_or_ip_dns_resolution(self):
        # Mock getaddrinfo to return private IP for an arbitrary hostname
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]):
            self.assertTrue(is_forbidden_host_or_ip("internal-service.example.org", resolve_dns=True))

        # Mock getaddrinfo to return public IP
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
            self.assertFalse(is_forbidden_host_or_ip("example.org", resolve_dns=True))

        # Mock getaddrinfo socket failure
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            self.assertFalse(is_forbidden_host_or_ip("unresolvable.example.org", resolve_dns=True))

    def test_validate_and_identify_url_ssrf_rejections(self):
        ssrf_urls = [
            "http://127.0.0.1/watch?v=1",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/video",
            "http://localhost/watch?v=1",
            "http://[::1]/watch?v=1",
            "http://service.internal/video",
        ]
        for url in ssrf_urls:
            with self.subTest(url=url):
                with self.assertRaises(URLValidationError) as ctx:
                    validate_and_identify_url(url)
                self.assertIn("jaringan internal atau lokal", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 6. Task ID validation
    # -------------------------------------------------------------------------
    def test_validate_task_id(self):
        # Valid task IDs
        self.assertIsNone(validate_task_id(None))
        self.assertIsNone(validate_task_id(""))
        self.assertEqual(validate_task_id("task-123"), "task-123")
        self.assertEqual(validate_task_id("c2a8f8d2-1111-4444-9999-abcdef123456"), "c2a8f8d2-1111-4444-9999-abcdef123456")
        self.assertEqual(validate_task_id("valid_ID_123"), "valid_ID_123")
        self.assertEqual(validate_task_id("a" * 64), "a" * 64)

        # Invalid task IDs
        invalid_ids = [
            "../etc/passwd",
            "<script>",
            "a" * 65,
            "task with space",
            "task;drop table",
            "task$id",
            "task/id",
            12345,  # non-string
        ]
        for bad_id in invalid_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(URLValidationError) as ctx:
                    validate_task_id(bad_id)  # type: ignore
                self.assertIn("Format ID tugas (task_id) tidak valid", str(ctx.exception))

    def test_download_request_task_id_schema_validation(self):
        # Valid task_id in DownloadRequest
        req = DownloadRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", task_id="valid-id-1")
        self.assertEqual(req.task_id, "valid-id-1")

        # Empty string turns to None
        req_empty = DownloadRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", task_id="")
        self.assertIsNone(req_empty.task_id)

        # Invalid task_id raises ValidationError
        with self.assertRaises(ValidationError):
            DownloadRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", task_id="../../secret")

    # -------------------------------------------------------------------------
    # 7. Filename sanitization and Content-Disposition
    # -------------------------------------------------------------------------
    def test_sanitize_filename(self):
        # Normal title
        self.assertEqual(sanitize_filename("Video Keren", "mp4"), "Video Keren.mp4")

        # Illegal characters in title
        self.assertEqual(sanitize_filename('Video: "Keren" <1> / 2 * ? |', "mp4"), "Video Keren 1 2.mp4")

        # Leading dot in extension
        self.assertEqual(sanitize_filename("Audio", ".mp3"), "Audio.mp3")

        # Empty title fallback
        self.assertEqual(sanitize_filename("", "mp4"), "Forte_Media.mp4")
        self.assertEqual(sanitize_filename("   ", "mp4"), "Forte_Media.mp4")

        # Very long title truncation (max 140 chars + .ext)
        long_title = "A" * 200
        sanitized = sanitize_filename(long_title, "mp4")
        self.assertTrue(len(sanitized.rsplit(".", 1)[0]) <= 140)
        self.assertTrue(sanitized.endswith(".mp4"))

    def test_build_content_disposition(self):
        # ASCII filename
        disp = build_content_disposition("My_Video.mp4")
        self.assertIn('attachment; filename="My_Video.mp4"', disp)
        self.assertIn("filename*=UTF-8''My_Video.mp4", disp)

        # Unicode filename with special chars
        disp_unicode = build_content_disposition("Lagu Indah 🎵.mp3")
        self.assertIn("attachment; filename=", disp_unicode)
        self.assertIn("filename*=UTF-8''", disp_unicode)
        self.assertIn("Lagu%20Indah", disp_unicode)


if __name__ == "__main__":
    unittest.main()
