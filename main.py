# Root entrypoint for Vercel auto-detection
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TRUST_PROXY_HEADERS", "true")

from app.main import app
