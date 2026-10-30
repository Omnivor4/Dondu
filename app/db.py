"""
Dondu — SQLite Persistent Storage Engine
Handles Device Analytics Recognition & Comments CRUD
"""

import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BASE_DIR

logger = logging.getLogger("dondu.db")

is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DATA_DIR: Path = Path("/tmp/dondu_data") if is_serverless else BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH: Path = DATA_DIR / "dondu.db"

# Inisialisasi Firebase Admin SDK jika file kredensial atau env var tersedia
firestore_client = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred = None
    service_account_raw = os.getenv("FIREBASE_SERVICE_ACCOUNT") or os.getenv("FIREBASE_CREDENTIALS")
    if service_account_raw:
        try:
            service_account_info = json.loads(service_account_raw)
            cred = credentials.Certificate(service_account_info)
        except Exception:
            if Path(service_account_raw).exists():
                cred = credentials.Certificate(service_account_raw)

    if not cred:
        key_files = list(BASE_DIR.glob("*firebase-adminsdk*.json"))
        if key_files:
            cred = credentials.Certificate(str(key_files[0]))

    if cred:
        try:
            firebase_app = firebase_admin.get_app()
        except ValueError:
            firebase_app = firebase_admin.initialize_app(cred)
        firestore_client = firestore.client()
        logger.info("Firebase Admin terhubung ke project: %s", firebase_app.project_id)
except Exception as exc:
    logger.debug("Firebase Admin tidak diinisialisasi: %s", exc)


def parse_device_info(user_agent: str, platform: str) -> Dict[str, str]:
    """Parse user-agent and platform into human-readable OS, browser, and device type."""
    ua = (user_agent or "").lower()
    plat = (platform or "").lower()

    # Detect Device Type
    device_type = "Desktop"
    if any(k in ua for k in ["mobi", "iphone", "android", "ipod"]):
        device_type = "Mobile"
    if any(k in ua for k in ["ipad", "tablet"]):
        device_type = "Tablet"

    # Detect OS
    os_name = "Unknown OS"
    if "windows" in ua or "win" in plat:
        os_name = "Windows"
    elif "android" in ua or "android" in plat:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ipod" in ua or "ios" in plat:
        os_name = "iOS"
    elif "mac" in ua or "mac" in plat:
        os_name = "macOS"
    elif "linux" in ua or "linux" in plat:
        os_name = "Linux"

    # Detect Browser
    browser_name = "Unknown Browser"
    if "edg" in ua:
        browser_name = "Microsoft Edge"
    elif "chrome" in ua and "safari" in ua:
        browser_name = "Google Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser_name = "Apple Safari"
    elif "firefox" in ua:
        browser_name = "Mozilla Firefox"
    elif "opera" in ua or "opr" in ua:
        browser_name = "Opera"

    return {
        "os": os_name,
        "browser": browser_name,
        "device_type": device_type,
    }


@contextmanager
def get_db_cursor():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Initializes tables and indexes, and pre-seeds default comments if empty."""
    with get_db_cursor() as cursor:
        # Device recognition & analytics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                visit_count INTEGER NOT NULL DEFAULT 1,
                os TEXT NOT NULL DEFAULT 'Unknown',
                browser TEXT NOT NULL DEFAULT 'Unknown',
                device_type TEXT NOT NULL DEFAULT 'Desktop',
                screen_res TEXT DEFAULT '',
                language TEXT DEFAULT '',
                last_ip TEXT DEFAULT ''
            )
        """)

        # Comments table with status & badges
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL,
                badge TEXT DEFAULT '',
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                device_id TEXT DEFAULT '',
                is_pinned INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_status ON comments(status)")

        # Pre-seed initial default comments if empty
        cursor.execute("SELECT COUNT(*) FROM comments")
        if cursor.fetchone()[0] == 0:
            now = datetime.now(timezone.utc).isoformat()
            default_comments = [
                (
                    "c_init_1",
                    "FarreL",
                    "Developer",
                    "Sistem pipeline Dondu v2.0 stabil. Kecepatan transcode H.264 & audio MP3 berjalan normal tanpa kompresi berlebih. Silakan tinggalkan kritik atau saran di sini!",
                    now,
                    "active",
                    "dev_device",
                    1,
                ),
                (
                    "c_init_2",
                    "Alex Pratama",
                    "User",
                    "UI-nya bersih banget tanpa gradasi dan warna terracotta-nya enak di mata. Unduh video TikTok jernih langsung masuk tanpa watermark.",
                    now,
                    "active",
                    "guest_device_1",
                    0,
                ),
                (
                    "c_init_3",
                    "Rian Saputra",
                    "",
                    "Fitur keyboard shortcut Ctrl+V sangat membantu buat paste cepat. Mantap!",
                    now,
                    "active",
                    "guest_device_2",
                    0,
                ),
            ]
            cursor.executemany(
                """
                INSERT INTO comments (id, author, badge, text, created_at, status, device_id, is_pinned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                default_comments,
            )
            conn.commit()


# --- Device Analytics Tracking Functions ---

def record_device_visit(
    device_id: str,
    user_agent: str,
    platform: str,
    screen_res: str = "",
    language: str = "",
    client_ip: str = "",
) -> Dict[str, Any]:
    """Records or updates a device visit."""
    clean_id = (device_id or "").strip()
    if not clean_id:
        clean_id = str(uuid.uuid4())

    parsed = parse_device_info(user_agent, platform)
    now = datetime.now(timezone.utc).isoformat()

    with get_db_cursor() as cursor:
        cursor.execute("SELECT visit_count FROM devices WHERE device_id = ?", (clean_id,))
        row = cursor.fetchone()

        if row:
            cursor.execute(
                """
                UPDATE devices
                SET last_seen_at = ?,
                    visit_count = visit_count + 1,
                    os = ?,
                    browser = ?,
                    device_type = ?,
                    screen_res = ?,
                    language = ?,
                    last_ip = ?
                WHERE device_id = ?
                """,
                (
                    now,
                    parsed["os"],
                    parsed["browser"],
                    parsed["device_type"],
                    screen_res,
                    language,
                    client_ip,
                    clean_id,
                ),
            )
            visit_count = row[0] + 1
        else:
            cursor.execute(
                """
                INSERT INTO devices (
                    device_id, first_seen_at, last_seen_at, visit_count,
                    os, browser, device_type, screen_res, language, last_ip
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_id,
                    now,
                    now,
                    parsed["os"],
                    parsed["browser"],
                    parsed["device_type"],
                    screen_res,
                    language,
                    client_ip,
                ),
            )
            visit_count = 1

    if firestore_client:
        try:
            firestore_client.collection("devices").document(clean_id).set({
                "device_id": clean_id,
                "last_seen_at": now,
                "visit_count": visit_count,
                "os": parsed["os"],
                "browser": parsed["browser"],
                "device_type": parsed["device_type"],
                "screen_res": screen_res,
                "language": language,
            }, merge=True)
        except Exception as e:
            logger.debug("Firestore device sync: %s", e)

    return {
        "device_id": clean_id,
        "visit_count": visit_count,
        "os": parsed["os"],
        "browser": parsed["browser"],
        "device_type": parsed["device_type"],
    }


def get_analytics_summary() -> Dict[str, Any]:
    """Returns analytics overview for the admin dashboard."""
    with get_db_cursor() as cursor:
        # Total unique devices
        cursor.execute("SELECT COUNT(*) FROM devices")
        total_devices = cursor.fetchone()[0]

        # Total visits
        cursor.execute("SELECT COALESCE(SUM(visit_count), 0) FROM devices")
        total_visits = cursor.fetchone()[0]

        # Active today
        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM devices WHERE last_seen_at LIKE ?", (f"{today_date}%",))
        devices_today = cursor.fetchone()[0]

        # OS breakdown
        cursor.execute("SELECT os, COUNT(*) as cnt FROM devices GROUP BY os ORDER BY cnt DESC")
        os_breakdown = [{"os": r["os"], "count": r["cnt"]} for r in cursor.fetchall()]

        # Device Type breakdown
        cursor.execute("SELECT device_type, COUNT(*) as cnt FROM devices GROUP BY device_type ORDER BY cnt DESC")
        device_type_breakdown = [{"type": r["device_type"], "count": r["cnt"]} for r in cursor.fetchall()]

        # Browser breakdown
        cursor.execute("SELECT browser, COUNT(*) as cnt FROM devices GROUP BY browser ORDER BY cnt DESC")
        browser_breakdown = [{"browser": r["browser"], "count": r["cnt"]} for r in cursor.fetchall()]

        # Recent 25 devices
        cursor.execute("""
            SELECT device_id, first_seen_at, last_seen_at, visit_count, os, browser, device_type, screen_res
            FROM devices
            ORDER BY last_seen_at DESC
            LIMIT 25
        """)
        recent_devices = [dict(r) for r in cursor.fetchall()]

        # Total comments
        cursor.execute("SELECT COUNT(*) FROM comments WHERE status != 'deleted'")
        total_comments = cursor.fetchone()[0]

    return {
        "total_devices": total_devices,
        "total_visits": total_visits,
        "devices_today": devices_today,
        "total_comments": total_comments,
        "os_breakdown": os_breakdown,
        "device_type_breakdown": device_type_breakdown,
        "browser_breakdown": browser_breakdown,
        "recent_devices": recent_devices,
    }


# --- Comments CRUD Functions ---

def get_public_comments() -> List[Dict[str, Any]]:
    """Returns active comments for the public user interface."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, author, badge, text, created_at, is_pinned
            FROM comments
            WHERE status = 'active'
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT 100
        """)
        return [dict(r) for r in cursor.fetchall()]


def get_all_comments_admin() -> List[Dict[str, Any]]:
    """Returns all comments (including hidden) for admin management."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, author, badge, text, created_at, status, device_id, is_pinned
            FROM comments
            WHERE status != 'deleted'
            ORDER BY is_pinned DESC, created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]


def add_comment(
    author: str,
    text: str,
    badge: str = "",
    device_id: str = "",
    is_pinned: bool = False,
    comment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds a new comment."""
    cid = comment_id or f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    now = datetime.now(timezone.utc).isoformat()
    clean_author = (author or "").strip()[:50] or "Anonymous"
    clean_text = (text or "").strip()[:500]
    clean_badge = (badge or "").strip()[:30]

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO comments (id, author, badge, text, created_at, status, device_id, is_pinned)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (cid, clean_author, clean_badge, clean_text, now, device_id, 1 if is_pinned else 0),
        )

    if firestore_client:
        try:
            firestore_client.collection("comments").document(cid).set({
                "id": cid,
                "author": clean_author,
                "badge": clean_badge,
                "text": clean_text,
                "created_at": now,
                "status": "active",
                "device_id": device_id,
                "is_pinned": bool(is_pinned),
            })
        except Exception as e:
            logger.debug("Firestore add_comment: %s", e)

    return {
        "id": cid,
        "author": clean_author,
        "badge": clean_badge,
        "text": clean_text,
        "created_at": now,
        "is_pinned": 1 if is_pinned else 0,
        "status": "active",
    }


def update_comment(
    comment_id: str,
    author: Optional[str] = None,
    text: Optional[str] = None,
    badge: Optional[str] = None,
    status: Optional[str] = None,
    is_pinned: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Updates an existing comment (admin function)."""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        if not row:
            return None

        current = dict(row)
        new_author = author.strip()[:50] if author is not None else current["author"]
        new_text = text.strip()[:500] if text is not None else current["text"]
        new_badge = badge.strip()[:30] if badge is not None else current["badge"]
        new_status = status.strip() if status is not None else current["status"]
        new_pinned = (1 if is_pinned else 0) if is_pinned is not None else current["is_pinned"]

        cursor.execute(
            """
            UPDATE comments
            SET author = ?, text = ?, badge = ?, status = ?, is_pinned = ?
            WHERE id = ?
            """,
            (new_author, new_text, new_badge, new_status, new_pinned, comment_id),
        )

        if firestore_client:
            try:
                firestore_client.collection("comments").document(comment_id).update({
                    "author": new_author,
                    "text": new_text,
                    "badge": new_badge,
                    "status": new_status,
                    "is_pinned": bool(new_pinned),
                })
            except Exception as e:
                logger.debug("Firestore update_comment: %s", e)

        return {
            "id": comment_id,
            "author": new_author,
            "text": new_text,
            "badge": new_badge,
            "status": new_status,
            "is_pinned": new_pinned,
            "created_at": current["created_at"],
        }


def delete_comment(comment_id: str) -> bool:
    """Soft deletes or hard deletes a comment."""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        deleted = cursor.rowcount > 0

    if deleted and firestore_client:
        try:
            firestore_client.collection("comments").document(comment_id).delete()
        except Exception as e:
            logger.debug("Firestore delete_comment: %s", e)

    return deleted


# Initialize on import
init_db()
