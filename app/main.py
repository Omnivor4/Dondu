import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.config import BASE_DIR, settings
from app.downloader import (
    DownloaderUserError,
    cleanup_expired_temp_dirs,
    download_media,
    extract_video_info,
    is_ffmpeg_available,
    progress_tracker,
    remove_temp_dir,
)
from app.rate_limiter import SlidingWindowRateLimiter
from app.schemas import (
    DownloadRequest,
    ProgressResponse,
    VideoInfoRequest,
    VideoInfoResponse,
)
from app.validators import (
    URLValidationError,
    build_content_disposition,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("forte.main")

rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
)


async def _periodic_cleanup_loop() -> None:
    """Tugas latar belakang untuk membersihkan folder unduhan sementara yang kedaluwarsa."""
    while True:
        try:
            await asyncio.sleep(settings.CLEANUP_INTERVAL_SECONDS)
            await asyncio.to_thread(cleanup_expired_temp_dirs)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Kesalahan pada tugas pembersihan berkala: %s", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(cleanup_expired_temp_dirs)

    ffmpeg_ok = is_ffmpeg_available()
    logger.info(
        "Memulai %s v%s | FFmpeg=%s | yt-dlp=%s | MaxDurasi=%dm | MaxUkuran=%dMB | RateLimit=%d/mnt",
        settings.APP_NAME,
        settings.VERSION,
        "Tersedia" if ffmpeg_ok else "TIDAK DITEMUKAN",
        yt_dlp.version.__version__,
        settings.MAX_DURATION_MINUTES,
        settings.MAX_FILE_SIZE_MB,
        settings.RATE_LIMIT_PER_MINUTE,
    )
    if not ffmpeg_ok:
        logger.warning(
            "FFmpeg belum terdeteksi di PATH sistem! Penggabungan video MP4 dan konversi MP3 membutuhkan FFmpeg."
        )

    cleanup_task = asyncio.create_task(_periodic_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        logger.info("Server %s dihentikan.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_TAGLINE,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)


@app.exception_handler(URLValidationError)
async def url_validation_exception_handler(request: Request, exc: URLValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(DownloaderUserError)
async def downloader_user_exception_handler(request: Request, exc: DownloaderUserError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Data permintaan tidak valid. Pastikan tautan dan pilihan format sudah benar."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Kesalahan tak terduga pada endpoint %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Terjadi kesalahan internal pada server. Silakan coba lagi beberapa saat."},
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """Endpoint pemeriksaan kesehatan layanan Forte."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "ffmpeg_installed": is_ffmpeg_available(),
        "yt_dlp_version": yt_dlp.version.__version__,
        "limits": {
            "max_duration_minutes": settings.MAX_DURATION_MINUTES,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
            "cleanup_max_age_minutes": settings.CLEANUP_MAX_AGE_MINUTES,
        },
    }


@app.post("/api/info", response_model=VideoInfoResponse, tags=["Downloader"])
async def get_video_info(payload: VideoInfoRequest, request: Request) -> VideoInfoResponse:
    """Memvalidasi tautan dan mengambil metadata serta daftar kualitas yang tersedia tanpa mengunduh."""
    rate_limiter.check(request)
    logger.info("Mengecek informasi media untuk permintaan baru.")
    return await asyncio.to_thread(extract_video_info, payload.url)


@app.get("/api/progress/{task_id}", response_model=ProgressResponse, tags=["Downloader"])
async def get_download_progress(task_id: str) -> ProgressResponse:
    """Mengambil status progres unduhan secara real-time berdasarkan task_id."""
    prog = progress_tracker.get(task_id)
    return ProgressResponse(
        task_id=task_id,
        status=prog.status,
        percent=prog.percent,
        message=prog.message,
    )


@app.post("/api/download", tags=["Downloader"])
async def download_video_or_audio(payload: DownloadRequest, request: Request) -> FileResponse:
    """Mengunduh video (MP4) atau audio (MP3) dan menghapusnya otomatis setelah dikirim ke browser."""
    rate_limiter.check(request)
    logger.info(
        "Memulai proses unduh | format=%s | kualitas=%s",
        payload.format_type,
        payload.quality,
    )

    result = await asyncio.to_thread(
        download_media,
        payload.url,
        payload.format_type,
        payload.quality,
        payload.task_id,
    )

    if not result.file_path.is_file():
        remove_temp_dir(result.temp_dir)
        raise HTTPException(status_code=500, detail="File hasil unduhan tidak ditemukan di server.")

    headers = {
        "Content-Disposition": build_content_disposition(result.download_filename),
        "X-Suggested-Filename": quote(result.download_filename, safe=""),
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    }

    return FileResponse(
        path=str(result.file_path),
        media_type=result.media_type,
        headers=headers,
        background=BackgroundTask(remove_temp_dir, result.temp_dir),
    )


STATIC_DIR: Path = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))

