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
if is_serverless:
    DATA_DIR: Path = Path("/tmp")
    DB_PATH: Path = Path("/tmp/dondu.db")
else:
    DATA_DIR: Path = BASE_DIR / "data"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
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
            cleaned = service_account_raw.strip().strip("'\"")
            service_account_info = json.loads(cleaned)
            if isinstance(service_account_info, dict) and "private_key" in service_account_info:
                service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(service_account_info)
        except Exception:
            if Path(service_account_raw).exists():
                cred = credentials.Certificate(service_account_raw)

    if not cred:
        key_files = list(BASE_DIR.glob("*firebase-adminsdk*.json"))
        if key_files:
            cred = credentials.Certificate(str(key_files[0]))

    if cred:
        if not firebase_admin._apps:
            firebase_app = firebase_admin.initialize_app(cred)
        else:
            firebase_app = firebase_admin.get_app()
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
    firestore_items: List[Dict[str, Any]] = []
    if firestore_client:
        try:
            docs = (
                firestore_client.collection("comments")
                .where("status", "==", "active")
                .order_by("is_pinned", direction=firestore.Query.DESCENDING)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(100)
                .stream()
            )
            for doc in docs:
                firestore_items.append(doc.to_dict())
        except Exception as e:
            logger.debug("Firestore get_public_comments: %s", e)

    if firestore_items:
        return firestore_items

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
    firestore_items: List[Dict[str, Any]] = []
    if firestore_client:
        try:
            docs = (
                firestore_client.collection("comments")
                .order_by("is_pinned", direction=firestore.Query.DESCENDING)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .stream()
            )
            for doc in docs:
                d = doc.to_dict()
                if d.get("status") != "deleted":
                    firestore_items.append(d)
        except Exception as e:
            logger.debug("Firestore get_all_comments_admin: %s", e)

    if firestore_items:
        try:
            with get_db_cursor() as cursor:
                for item in firestore_items:
                    cursor.execute(
                        """
                        INSERT INTO comments (id, author, badge, text, created_at, status, device_id, is_pinned)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            author = excluded.author,
                            badge = excluded.badge,
                            text = excluded.text,
                            status = excluded.status,
                            is_pinned = excluded.is_pinned
                        """,
                        (
                            item.get("id"),
                            item.get("author", "Anonymous"),
                            item.get("badge", ""),
                            item.get("text", ""),
                            item.get("created_at", datetime.now(timezone.utc).isoformat()),
                            item.get("status", "active"),
                            item.get("device_id", ""),
                            1 if item.get("is_pinned") else 0,
                        ),
                    )
        except Exception as e:
            logger.debug("SQLite sync from firestore: %s", e)
        return firestore_items

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
    """Updates an existing comment or gracefully upserts if on serverless fresh container."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()

        if row:
            current = dict(row)
            new_author = author.strip()[:50] if author is not None else current["author"]
            new_text = text.strip()[:500] if text is not None else current["text"]
            new_badge = badge.strip()[:30] if badge is not None else current["badge"]
            new_status = status.strip() if status is not None else current["status"]
            new_pinned = (1 if is_pinned else 0) if is_pinned is not None else current["is_pinned"]
            created_at = current["created_at"]
        else:
            # Jika di container serverless baru belum tersimpan di SQLite lokal, lakukan upsert toleran
            new_author = author.strip()[:50] if author is not None and author.strip() else "Anonymous"
            new_text = text.strip()[:500] if text is not None and text.strip() else "—"
            new_badge = badge.strip()[:30] if badge is not None else ""
            new_status = status.strip() if status is not None else "active"
            new_pinned = (1 if is_pinned else 0) if is_pinned is not None else 0
            created_at = now

        cursor.execute(
            """
            INSERT INTO comments (id, author, badge, text, created_at, status, device_id, is_pinned)
            VALUES (?, ?, ?, ?, ?, ?, '', ?)
            ON CONFLICT(id) DO UPDATE SET
                author = excluded.author,
                text = excluded.text,
                badge = excluded.badge,
                status = excluded.status,
                is_pinned = excluded.is_pinned
            """,
            (comment_id, new_author, new_badge, new_text, created_at, new_status, new_pinned),
        )

        if firestore_client:
            try:
                firestore_client.collection("comments").document(comment_id).set({
                    "id": comment_id,
                    "author": new_author,
                    "text": new_text,
                    "badge": new_badge,
                    "status": new_status,
                    "is_pinned": bool(new_pinned),
                    "created_at": created_at,
                }, merge=True)
            except Exception as e:
                logger.debug("Firestore update_comment: %s", e)

        return {
            "id": comment_id,
            "author": new_author,
            "text": new_text,
            "badge": new_badge,
            "status": new_status,
            "is_pinned": new_pinned,
            "created_at": created_at,
        }


def delete_comment(comment_id: str) -> bool:
    """Soft deletes or hard deletes a comment idempotently."""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))

    if firestore_client:
        try:
            firestore_client.collection("comments").document(comment_id).delete()
        except Exception as e:
            logger.debug("Firestore delete_comment: %s", e)

    return True


# Initialize on import safely
try:
    init_db()
except Exception as _db_err:
    logger.warning("Gagal inisialisasi awal database SQLite: %s", _db_err)
