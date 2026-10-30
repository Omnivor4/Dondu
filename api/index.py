import os
import sys
import traceback
from pathlib import Path

# Daftarkan root proyek ke sys.path untuk lingkungan serverless Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TRUST_PROXY_HEADERS", "true")

try:
    from app.main import app
    handler = app
except Exception as exc:
    err_tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    error_app = FastAPI()

    @error_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"])
    async def crash_handler(path: str = ""):
        return HTMLResponse(
            content=f"""
            <div style="font-family:sans-serif;padding:30px;background:#fff1f0;border:2px solid #ffa39e;border-radius:8px;max-width:800px;margin:40px auto;">
                <h2 style="color:#cf1322;margin-top:0;">Dondu Startup Exception on Vercel</h2>
                <p><strong>Error:</strong> {exc}</p>
                <pre style="background:#2d1614;color:#fca5a5;padding:15px;border-radius:6px;overflow:auto;font-size:13px;">{err_tb}</pre>
            </div>
            """,
            status_code=200,
        )

    handler = error_app
    app = error_app
