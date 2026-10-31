import os
import sys
from pathlib import Path

# Daftarkan root proyek ke sys.path untuk lingkungan serverless Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TRUST_PROXY_HEADERS", "true")

try:
    from app.main import app
except Exception as exc:
    import logging

    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("dondu.startup").exception("Dondu Serverless Startup Exception: %s", exc)

    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"])
    async def crash_handler(path: str = ""):
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>500 - Layanan Tidak Tersedia | Dondu</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #FFF9F6;
            color: #2D1B18;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }
        .error-card {
            background: #FFFFFF;
            border: 1.5px solid #E8BBA6;
            border-radius: 12px;
            padding: 40px;
            max-width: 480px;
            text-align: center;
            box-shadow: 0 4px 16px rgba(168, 90, 66, 0.08);
        }
        h1 {
            color: #A85A42;
            font-size: 1.5rem;
            margin-top: 0;
            margin-bottom: 12px;
        }
        p {
            color: #5C4A47;
            font-size: 0.95rem;
            line-height: 1.5;
            margin: 0 0 20px 0;
        }
        .badge {
            display: inline-block;
            padding: 6px 14px;
            background: #FCEFEA;
            color: #A85A42;
            font-size: 0.82rem;
            font-weight: 600;
            border-radius: 20px;
        }
    </style>
</head>
<body>
    <div class="error-card">
        <h1>Layanan Sedang Mengalami Kendala</h1>
        <p>Dondu engine sedang melakukan inisialisasi atau mengalami kendala sementara. Silakan segarkan halaman dalam beberapa saat.</p>
        <span class="badge">HTTP 500 Internal Server Error</span>
    </div>
</body>
</html>""",
            status_code=500,
        )
