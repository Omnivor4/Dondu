import asyncio
import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

# Pastikan root proyek masuk ke sys.path untuk lingkungan serverless seperti Vercel
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
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
from app.db import (
    add_comment,
    delete_comment,
    get_all_comments_admin,
    get_analytics_summary,
    get_public_comments,
    record_device_visit,
    update_comment,
)
from app.rate_limiter import SlidingWindowRateLimiter
from app.schemas import (
    AdminLoginRequest,
    CommentCreateRequest,
    CommentUpdateRequest,
    DeviceTrackRequest,
    DownloadRequest,
    ProgressResponse,
    VideoInfoRequest,
    VideoInfoResponse,
)
from app.validators import (
    URLValidationError,
    build_content_disposition,
    validate_task_id,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("dondu.main")

rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
    trust_proxy_headers=settings.TRUST_PROXY_HEADERS,
)

progress_rate_limiter = SlidingWindowRateLimiter(
    max_requests=120,
    window_seconds=60,
    trust_proxy_headers=settings.TRUST_PROXY_HEADERS,
)

info_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFO)
download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)


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
    try:
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    try:
        await asyncio.to_thread(cleanup_expired_temp_dirs)
    except Exception:
        pass

    ffmpeg_ok = is_ffmpeg_available()
    dur_str = f"{settings.MAX_DURATION_MINUTES}m" if settings.MAX_DURATION_MINUTES > 0 else "Tanpa Batas"
    size_str = f"{settings.MAX_FILE_SIZE_MB}MB" if settings.MAX_FILE_SIZE_MB > 0 else "Tanpa Batas"
    logger.info(
        "Memulai %s v%s | FFmpeg=%s | yt-dlp=%s | MaxDurasi=%s | MaxUkuran=%s | RateLimit=%d/mnt",
        settings.APP_NAME,
        settings.VERSION,
        "Tersedia" if ffmpeg_ok else "TIDAK DITEMUKAN",
        yt_dlp.version.__version__,
        dur_str,
        size_str,
        settings.RATE_LIMIT_PER_MINUTE,
    )
    if not ffmpeg_ok:
        logger.warning(
            "FFmpeg belum terdeteksi di PATH sistem! Penggabungan video MP4 dan konversi MP3 membutuhkan FFmpeg."
        )

    # Hanya jalankan background cleanup task pada server persisten (bukan serverless Vercel)
    is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    cleanup_task = None
    if not is_serverless:
        cleanup_task = asyncio.create_task(_periodic_cleanup_loop())

    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        logger.info("Server %s dihentikan.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_TAGLINE,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    redoc_url=None,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' https: http: data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


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
    """Endpoint pemeriksaan kesehatan layanan Dondu."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "ffmpeg_installed": is_ffmpeg_available(),
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
    try:
        await asyncio.wait_for(info_semaphore.acquire(), timeout=2.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server sedang sibuk memproses banyak permintaan. Silakan coba lagi beberapa detik.",
        )
    try:
        logger.info("Mengecek informasi media untuk permintaan baru.")
        return await asyncio.to_thread(extract_video_info, payload.url)
    finally:
        info_semaphore.release()


@app.get("/api/progress/{task_id}", response_model=ProgressResponse, tags=["Downloader"])
async def get_download_progress(task_id: str, request: Request) -> ProgressResponse:
    """Mengambil status progres unduhan secara real-time berdasarkan task_id."""
    progress_rate_limiter.check(request)
    validate_task_id(task_id)
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
    validate_task_id(payload.task_id)

    try:
        await asyncio.wait_for(download_semaphore.acquire(), timeout=2.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server sedang memproses batas maksimum unduhan bersamaan. Silakan tunggu beberapa detik lalu coba lagi.",
        )

    try:
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
    finally:
        download_semaphore.release()

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
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

def _resolve_static_path(filename: str) -> Path:
    direct = STATIC_DIR / filename
    if direct.is_file():
        return direct
    alt = Path("static") / filename
    if alt.is_file():
        return alt.resolve()
    return direct

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def verify_admin_key(request: Request) -> bool:
    key = request.headers.get("X-Admin-Key") or request.query_params.get("key")
    if not key or key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Kunci otorisasi admin tidak valid.")
    return True


@app.get("/", include_in_schema=False)
async def serve_index() -> Response:
    index_file = _resolve_static_path("index.html")
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="File index.html tidak ditemukan.")
    try:
        content = index_file.read_text(encoding="utf-8")
        return HTMLResponse(content=content, headers={"Cache-Control": "public, max-age=300"})
    except Exception:
        return FileResponse(str(index_file))


@app.get("/DonduFarrel", include_in_schema=False)
async def serve_admin_page() -> Response:
    """Dashboard Admin khusus dengan URL tersembunyi /DonduFarrel."""
    admin_html = _resolve_static_path("admin.html")
    if not admin_html.is_file():
        raise HTTPException(status_code=404, detail="Halaman admin belum dibuat.")
    try:
        content = admin_html.read_text(encoding="utf-8")
        return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
    except Exception:
        return FileResponse(str(admin_html))


# --- Analytics & Device Tracking ---

@app.post("/api/track-device", tags=["Analytics"])
async def track_device_endpoint(payload: DeviceTrackRequest, request: Request):
    """Merekam jejak perangkat unik untuk analitik dashboard admin."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = payload.user_agent or request.headers.get("user-agent", "")
    info = await asyncio.to_thread(
        record_device_visit,
        device_id=payload.device_id or "",
        user_agent=user_agent,
        platform=payload.platform or "",
        screen_res=payload.screen_res or "",
        language=payload.language or "",
        client_ip=client_ip,
    )
    return {"status": "ok", "device": info}


# --- Public Comments API ---

@app.get("/api/comments", tags=["Comments"])
async def list_comments():
    """Mengambil daftar komentar publik terverifikasi."""
    comments = await asyncio.to_thread(get_public_comments)
    return {"comments": comments, "total": len(comments)}


@app.post("/api/comments", tags=["Comments"])
async def create_comment_endpoint(payload: CommentCreateRequest, request: Request):
    """Menambahkan komentar baru dari pengguna dengan validasi dan rate limiting."""
    rate_limiter.check(request)
    created = await asyncio.to_thread(
        add_comment,
        author=payload.author,
        text=payload.text,
        device_id=payload.device_id or "",
    )
    return {"status": "ok", "comment": created}


# --- Admin Dashboard Endpoints (Protected) ---

@app.post("/api/admin/login", tags=["Admin"])
async def admin_login_endpoint(payload: AdminLoginRequest):
    """Verifikasi passkey untuk masuk ke dashboard admin."""
    if payload.passkey != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Passkey admin salah.")
    return {"status": "ok", "token": settings.ADMIN_SECRET_KEY}


@app.get("/api/admin/analytics", tags=["Admin"])
async def admin_analytics_endpoint(request: Request):
    """Ringkasan statistik perangkat dan pengunjung web."""
    verify_admin_key(request)
    summary = await asyncio.to_thread(get_analytics_summary)
    return summary


@app.get("/api/admin/comments", tags=["Admin"])
async def admin_list_comments_endpoint(request: Request):
    """Mengambil semua komentar (termasuk yang disembunyikan) untuk manajemen CRUD."""
    verify_admin_key(request)
    comments = await asyncio.to_thread(get_all_comments_admin)
    return {"comments": comments, "total": len(comments)}


@app.post("/api/admin/comments", tags=["Admin"])
async def admin_create_announcement(payload: CommentCreateRequest, request: Request):
    """Admin membuat komentar atau pengumuman resmi bertanda Developer/Admin."""
    verify_admin_key(request)
    created = await asyncio.to_thread(
        add_comment,
        author=payload.author,
        text=payload.text,
        badge="Developer",
        is_pinned=True,
    )
    return {"status": "ok", "comment": created}


@app.put("/api/admin/comments/{comment_id}", tags=["Admin"])
async def admin_update_comment_endpoint(comment_id: str, payload: CommentUpdateRequest, request: Request):
    """Admin memperbarui status, teks, badge, atau pin komentar."""
    verify_admin_key(request)
    updated = await asyncio.to_thread(
        update_comment,
        comment_id=comment_id,
        author=payload.author,
        text=payload.text,
        badge=payload.badge,
        status=payload.status,
        is_pinned=payload.is_pinned,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Komentar tidak ditemukan.")
    return {"status": "ok", "comment": updated}


@app.delete("/api/admin/comments/{comment_id}", tags=["Admin"])
async def admin_delete_comment_endpoint(comment_id: str, request: Request):
    """Admin menghapus komentar spam atau tidak pantas."""
    verify_admin_key(request)
    deleted = await asyncio.to_thread(delete_comment, comment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Komentar tidak ditemukan.")
    return {"status": "ok", "deleted_id": comment_id}


