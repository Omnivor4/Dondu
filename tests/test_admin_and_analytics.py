import re
import unittest
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient

from app.config import BASE_DIR, settings
from app.main import app


class TestAdminDashboardAndAnalytics(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.admin_key = settings.ADMIN_SECRET_KEY
        self.static_dir = BASE_DIR / "static"

    def test_admin_route_custom_url(self):
        """Pastikan dashboard admin dapat diakses di /DonduFarrel dan TIDAK di /admin."""
        # /DonduFarrel harus 200 OK
        res = self.client.get("/DonduFarrel")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("Dondu Central Command", res.text)
        self.assertIn("RESTRICTED /DonduFarrel", res.text)

        # /admin harus 404 (tidak boleh terbuka)
        res_admin = self.client.get("/admin")
        self.assertEqual(res_admin.status_code, 404)

    def test_logo_vector_asset(self):
        """Pastikan aset logo kustom dondu-logo.svg tersedia dan sesuai palet."""
        logo_path = self.static_dir / "dondu-logo.svg"
        self.assertTrue(logo_path.is_file(), "File dondu-logo.svg harus ada di folder static")

        content = logo_path.read_text(encoding="utf-8")
        self.assertIn("<svg", content)
        self.assertIn("#E8BBA6", content)
        self.assertIn("#A85A42", content)

        # Pastikan tidak ada gradasi atau warna hijau
        self.assertNotIn("linear-gradient", content)
        self.assertNotIn("radial-gradient", content)
        self.assertNotIn("#10b981", content)
        self.assertNotIn("#059669", content)

    def test_track_device_endpoint(self):
        """Pastikan pelacakan perangkat merekam OS, browser, dan kunjungan."""
        payload = {
            "device_id": "test_device_unit_999",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "platform": "Win32",
            "screen_res": "1920x1080",
            "language": "id-ID",
        }
        res = self.client.post("/api/track-device", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data["device"]["os"], "Windows")
        self.assertEqual(data["device"]["browser"], "Google Chrome")
        self.assertEqual(data["device"]["device_type"], "Desktop")

    def test_admin_analytics_auth(self):
        """Pastikan endpoint analitik terlindungi kunci otorisasi admin."""
        # Tanpa kunci -> 401
        res = self.client.get("/api/admin/analytics")
        self.assertEqual(res.status_code, 401)

        # Dengan kunci salah -> 401
        res_wrong = self.client.get("/api/admin/analytics", headers={"X-Admin-Key": "wrong_key"})
        self.assertEqual(res_wrong.status_code, 401)

        # Dengan kunci benar -> 200
        res_ok = self.client.get("/api/admin/analytics", headers={"X-Admin-Key": self.admin_key})
        self.assertEqual(res_ok.status_code, 200)
        analytics = res_ok.json()
        self.assertIn("total_devices", analytics)
        self.assertIn("total_visits", analytics)
        self.assertIn("devices_today", analytics)
        self.assertIn("os_breakdown", analytics)

    def test_comments_crud_lifecycle(self):
        """Uji siklus lengkap CRUD komentar: Create -> List -> Update -> Delete."""
        # 1. Buat komentar publik
        create_payload = {
            "author": "Unit Tester",
            "text": "Komentar otomatis pengujian unit test.",
            "device_id": "test_device_unit_999",
        }
        res_create = self.client.post("/api/comments", json=create_payload)
        self.assertEqual(res_create.status_code, 200)
        created_comment = res_create.json()["comment"]
        comment_id = created_comment["id"]

        # 2. Ambil daftar publik
        res_list = self.client.get("/api/comments")
        self.assertEqual(res_list.status_code, 200)
        comments = res_list.json()["comments"]
        found = any(c["id"] == comment_id for c in comments)
        self.assertTrue(found, "Komentar baru harus muncul di daftar publik")

        # 3. Update komentar via Admin
        update_payload = {
            "badge": "Verified Tester",
            "is_pinned": True,
            "status": "active",
        }
        res_update = self.client.put(
            f"/api/admin/comments/{comment_id}",
            json=update_payload,
            headers={"X-Admin-Key": self.admin_key},
        )
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.json()["comment"]["badge"], "Verified Tester")
        self.assertEqual(res_update.json()["comment"]["is_pinned"], 1)

        # 4. Hapus komentar via Admin
        res_delete = self.client.delete(
            f"/api/admin/comments/{comment_id}",
            headers={"X-Admin-Key": self.admin_key},
        )
        self.assertEqual(res_delete.status_code, 200)
        self.assertEqual(res_delete.json()["deleted_id"], comment_id)

        # 5. Pastikan komentar sudah terhapus
        res_list_after = self.client.get("/api/comments")
        comments_after = res_list_after.json()["comments"]
        self.assertFalse(any(c["id"] == comment_id for c in comments_after))

    def test_comment_update_upsert_serverless_coldstart(self):
        """Pastikan update komentar pada container serverless baru yang belum punya ID di SQLite tidak 404 (UPSERT)."""
        phantom_id = f"c_phantom_{int(datetime.now().timestamp() * 1000)}"
        update_payload = {
            "author": "Admin Recovery",
            "text": "Konten komentar yang dipulihkan pada serverless fresh instance.",
            "badge": "Admin",
            "is_pinned": True,
            "status": "active",
        }
        res = self.client.put(
            f"/api/admin/comments/{phantom_id}",
            json=update_payload,
            headers={"X-Admin-Key": self.admin_key},
        )
        self.assertEqual(res.status_code, 200, "Update komentar tidak boleh 404 pada container serverless baru")
        data = res.json()["comment"]
        self.assertEqual(data["id"], phantom_id)
        self.assertEqual(data["author"], "Admin Recovery")
        self.assertEqual(data["text"], "Konten komentar yang dipulihkan pada serverless fresh instance.")

        # Cleanup
        self.client.delete(f"/api/admin/comments/{phantom_id}", headers={"X-Admin-Key": self.admin_key})
