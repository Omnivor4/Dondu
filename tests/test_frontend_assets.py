import re
import unittest

from fastapi.testclient import TestClient

from app.config import BASE_DIR
from app.main import app


class TestFrontendAssetsAndCleanliness(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.static_dir = BASE_DIR / "static"

    def test_serve_index_html(self):
        """Pastikan endpoint root mengembalikan index.html dengan status 200 dan tema peach #E8BBA6."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        content = res.text

        # Cek theme-color tone yang tepat dari gambar user
        self.assertIn('<meta name="theme-color" content="#E8BBA6" />', content)

        # Pastikan tidak ada warna hijau lama
        self.assertNotIn("#10b981", content)
        self.assertNotIn("#059669", content)
        self.assertNotIn("#047857", content)
        self.assertNotIn("#22c55e", content)

        # Cek elemen shortcut hint dengan ID
        self.assertIn('id="shortcutHint"', content)

    def test_serve_styles_css(self):
        """Pastikan styles.css disajikan dengan benar dan memenuhi kriteria tanpa hijau dan tanpa gradasi."""
        res = self.client.get("/static/styles.css")
        self.assertEqual(res.status_code, 200)
        css = res.text

        # Cek warna aksen utama flat solid #E8BBA6
        self.assertIn("--accent: #E8BBA6;", css)

        # Pastikan tidak ada kode warna hijau
        green_patterns = [
            r"#10b981",
            r"#059669",
            r"#047857",
            r"#22c55e",
            r"#16a34a",
            r"#15803d",
            r"emerald",
            r"rgba\(16,\s*185,\s*129",
        ]
        for pat in green_patterns:
            self.assertFalse(
                re.search(pat, css, re.IGNORECASE),
                f"Ditemukan kode/nama warna hijau di CSS: {pat}",
            )

        # Pastikan tidak ada fungsi gradasi sama sekali
        gradient_funcs = [
            r"linear-gradient\(",
            r"radial-gradient\(",
            r"conic-gradient\(",
            r"repeating-linear-gradient\(",
            r"repeating-radial-gradient\(",
        ]
        for grad in gradient_funcs:
            self.assertFalse(
                re.search(grad, css, re.IGNORECASE),
                f"Ditemukan gradasi di CSS: {grad}",
            )

        # Pastikan progress-fill memiliki kontras tinggi di light mode
        self.assertIn("background-color: var(--accent-dark);", css)

        # Pastikan tersedia focus-visible styles untuk aksesibilitas enterprise
        self.assertIn(":focus-visible", css)

    def test_serve_app_js(self):
        """Pastikan app.js disajikan dan mengimplementasikan shortcut keyboard serta state management."""
        res = self.client.get("/static/app.js")
        self.assertEqual(res.status_code, 200)
        js = res.text

        # Tidak ada warna hijau
        self.assertNotIn("#10b981", js)
        self.assertNotIn("#059669", js)

        # Shortcut handling (Ctrl+V / Cmd+V, Escape, /)
        self.assertIn("ctrlKey", js)
        self.assertIn("metaKey", js)
        self.assertIn('"v"', js)
        self.assertIn('"Escape"', js)
        self.assertIn('"/"', js)

        # Stale state dismissal
        self.assertIn("State.reset()", js)

    def test_unnecessary_files_deleted(self):
        """Pastikan file-file tidak penting seperti .env.example, AUDIT_REPORT.md, README.md, dan docs telah dihapus."""
        self.assertFalse((BASE_DIR / ".env.example").exists(), ".env.example seharusnya sudah dihapus")
        self.assertFalse((BASE_DIR / "AUDIT_REPORT.md").exists(), "AUDIT_REPORT.md seharusnya sudah dihapus")
        self.assertFalse((BASE_DIR / "README.md").exists(), "README.md seharusnya sudah dihapus")
        self.assertFalse((BASE_DIR / "docs").exists(), "Folder docs seharusnya sudah dihapus")

    def test_no_apk_or_mobile_artifacts(self):
        """Pastikan tidak ada artefak build APK atau AAB di repository."""
        apk_files = list(BASE_DIR.glob("**/*.apk"))
        aab_files = list(BASE_DIR.glob("**/*.aab"))
        self.assertEqual(apk_files, [], f"Ditemukan file APK tidak diinginkan: {apk_files}")
        self.assertEqual(aab_files, [], f"Ditemukan file AAB tidak diinginkan: {aab_files}")
