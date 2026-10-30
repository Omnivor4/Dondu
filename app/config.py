import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    APP_NAME: str = "Dondu"
    APP_TAGLINE: str = "Unduh video & MP3 dengan cepat."
    VERSION: str = "1.0.0"

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Keamanan dan proxy
    TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")
    ENABLE_DOCS: bool = os.getenv("ENABLE_DOCS", "false").lower() in ("1", "true", "yes")
    MAX_CONCURRENT_INFO: int = int(os.getenv("MAX_CONCURRENT_INFO", "8"))
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
    RESOLVE_DNS_SSRF_CHECK: bool = os.getenv("RESOLVE_DNS_SSRF_CHECK", "false").lower() in ("1", "true", "yes")

    # Batas durasi maksimum dalam menit (default: 0 = tanpa batas / unlimited)
    MAX_DURATION_MINUTES: int = int(os.getenv("MAX_DURATION_MINUTES", "0"))
    MAX_DURATION_SECONDS: int = MAX_DURATION_MINUTES * 60

    # Batas ukuran file maksimum dalam MB (default: 0 = tanpa batas / unlimited)
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "0"))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

    # Rate limit per IP per menit (default: 10 req/menit)
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

    # Direktori unduhan sementara dan jadwal pembersihan
    # Di lingkungan serverless seperti Vercel/AWS Lambda, hanya /tmp yang dapat ditulis (writable)
    _default_temp = "/tmp/dondu_downloads" if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") else str(BASE_DIR / "temp_downloads")
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", _default_temp)).resolve()
    CLEANUP_MAX_AGE_MINUTES: int = int(os.getenv("CLEANUP_MAX_AGE_MINUTES", "15"))
    CLEANUP_MAX_AGE_SECONDS: int = CLEANUP_MAX_AGE_MINUTES * 60
    CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "120"))

    # Opsional: file cookies Netscape untuk platform yang membutuhkan sesi
    COOKIES_FILE: str = os.getenv("COOKIES_FILE", "").strip()

    # Opsional: lokasi binary FFmpeg kustom
    FFMPEG_LOCATION: str = os.getenv("FFMPEG_LOCATION", "").strip()

    # Pilihan kualitas standar
    STANDARD_VIDEO_HEIGHTS: tuple[int, ...] = (360, 480, 720, 1080, 1440, 2160)
    ALLOWED_AUDIO_BITRATES: tuple[int, ...] = (128, 192, 256, 320)

    # Admin Dashboard Key (Protected Route /DonduFarrel)
    ADMIN_SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "farrel2026")


settings = Settings()
try:
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

