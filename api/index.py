import os
import sys
from pathlib import Path

# Daftarkan root proyek ke sys.path untuk lingkungan serverless Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TRUST_PROXY_HEADERS", "true")

from app.main import app

# Entrypoint ASGI untuk Vercel Serverless Function
handler = app
app = app
