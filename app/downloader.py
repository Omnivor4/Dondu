import logging
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.config import settings
from app.schemas import QualityOption, VideoInfoResponse
from app.validators import sanitize_filename, validate_and_identify_url

logger = logging.getLogger("forte.downloader")


class DownloaderUserError(Exception):
    """Error ramah pengguna yang aman ditampilkan ke klien tanpa stack trace."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class TaskProgress:
    status: str
    percent: float
    message: str
    updated_at: float


class ProgressTracker:
    """Penyimpanan progres unduhan sementara di memori (tanpa menyimpan data pengguna)."""

    def __init__(self) -> None:
        self._store: dict[str, TaskProgress] = {}
        self._lock = Lock()

    def update(self, task_id: Optional[str], status: str, percent: float, message: str) -> None:
        if not task_id:
            return
        with self._lock:
            self._store[task_id] = TaskProgress(
                status=status,
                percent=round(max(0.0, min(100.0, percent)), 1),
                message=message,
                updated_at=time.monotonic(),
            )

    def get(self, task_id: str) -> TaskProgress:
        with self._lock:
            item = self._store.get(task_id)
            if item is None:
                return TaskProgress(status="pending", percent=0.0, message="Menyiapkan unduhan...", updated_at=time.monotonic())
            return item

    def cleanup_old(self, max_age_seconds: int = 600) -> None:
        cutoff = time.monotonic() - max_age_seconds
        with self._lock:
            stale = [k for k, v in self._store.items() if v.updated_at < cutoff]
            for k in stale:
                self._store.pop(k, None)


progress_tracker = ProgressTracker()


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def format_duration(seconds: Optional[int | float]) -> str:
    if seconds is None or seconds <= 0:
        return "Langsung / Tidak diketahui"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def map_ytdlp_error(exc: Exception) -> DownloaderUserError:
    """Mengubah exception teknis yt-dlp/FFmpeg menjadi pesan bahasa Indonesia yang ramah pengguna."""
    if isinstance(exc, DownloaderUserError):
        return exc

    raw = str(exc).lower()

    # 1. FFmpeg tidak ditemukan
    if "ffmpeg" in raw and ("not found" in raw or "not installed" in raw or "aborting" in raw):
        return DownloaderUserError(
            "FFmpeg tidak ditemukan di server. Pastikan FFmpeg sudah terpasang di sistem agar penggabungan video dan konversi MP3 dapat berjalan.",
            status_code=500,
        )

    # 2. Konten ber-DRM
    if any(k in raw for k in ("drm", "widevine", "playready", "fairplay", "protected by drm")):
        return DownloaderUserError(
            "Konten ini dilindungi DRM dan tidak dapat diunduh sesuai kebijakan layanan.",
            status_code=403,
        )

    # 3. Konten dibatasi usia atau wilayah (Geo-blocked / Age-restricted)
    if any(
        k in raw
        for k in (
            "age-restricted",
            "confirm your age",
            "inappropriate for some users",
            "sign in to confirm your age",
            "not available in your country",
            "blocked in your country",
            "geo-restricted",
            "has not made this video available in your country",
        )
    ):
        return DownloaderUserError(
            "Video ini dibatasi usia atau tidak tersedia di wilayah server saat ini.",
            status_code=403,
        )

    # 4. Video privat atau butuh login / cookies
    if any(
        k in raw
        for k in (
            "private video",
            "video is private",
            "login required",
            "logged-in",
            "you must be logged in",
            "members-only",
            "subscribers-only",
            "this content isn't available",
            "instagram API is not granting access",
            "cookies",
            "authentication",
        )
    ):
        return DownloaderUserError(
            "Video ini bersifat privat atau membutuhkan login akun. Pastikan konten bersifat publik.",
            status_code=403,
        )

    # 5. Platform memblokir / Rate limit / Proteksi Bot
    if any(
        k in raw
        for k in (
            "http error 429",
            "too many requests",
            "confirm you’re not a bot",
            "confirm you're not a bot",
            "http error 403",
            "cloudflare",
            "captcha",
            "rate-limit",
            "blocked",
        )
    ):
        return DownloaderUserError(
            "Platform sumber sedang membatasi permintaan otomatis saat ini. Silakan coba lagi beberapa saat atau perbarui yt-dlp ke versi terbaru.",
            status_code=503,
        )

    # 6. Ukuran atau durasi melampaui batas
    if "max-filesize" in raw or "file is larger than max" in raw or "melebihi batas ukuran" in raw:
        return DownloaderUserError(
            f"Ukuran file video melebihi batas maksimum server ({settings.MAX_FILE_SIZE_MB} MB).",
            status_code=413,
        )

    # 7. Video dihapus / tidak ditemukan / URL salah
    if any(
        k in raw
        for k in (
            "video unavailable",
            "has been removed",
            "does not exist",
            "http error 404",
            "unsupported url",
            "no video formats found",
            " there is no video in this post",
            "unable to extract",
        )
    ):
        return DownloaderUserError(
            "Video tidak ditemukan, tidak memuat media video, atau telah dihapus oleh pemiliknya.",
            status_code=404,
        )

    logger.warning("yt-dlp gagal memproses permintaan: %s", type(exc).__name__)
    return DownloaderUserError(
        "Gagal memproses media dari tautan tersebut. Pastikan tautan menuju ke video publik yang aktif.",
        status_code=400,
    )


def _base_ytdlp_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "geo_bypass": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "nocheckcertificate": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    }
    if settings.COOKIES_FILE and Path(settings.COOKIES_FILE).is_file():
        opts["cookiefile"] = settings.COOKIES_FILE
    return opts


def _resolve_bucket_height(fmt: dict[str, Any]) -> Optional[int]:
    """
    Menentukan bucket kualitas standar (360, 480, 720, 1080, 1440, 2160)
    baik untuk video lanskap (16:9) maupun vertikal seperti Shorts/Reels/TikTok (9:16).
    """
    height = fmt.get("height")
    width = fmt.get("width")
    if not isinstance(height, int) or height <= 0:
        return None

    short_side = min(width, height) if isinstance(width, int) and width > 0 else height

    # Cocokkan ke resolusi standar terdekat dengan toleransi wajar
    for std in settings.STANDARD_VIDEO_HEIGHTS:
        if abs(short_side - std) <= 36 or abs(height - std) <= 36:
            return std

    return None


def _build_quality_options(formats: list[dict[str, Any]]) -> list[QualityOption]:
    quality_labels = {
        2160: "2160p (4K)",
        1440: "1440p (2K)",
        1080: "1080p (Full HD)",
        720: "720p (HD)",
        480: "480p",
        360: "360p",
    }

    found_buckets: dict[int, Optional[int]] = {}
    for fmt in formats:
        vcodec = fmt.get("vcodec")
        if not vcodec or vcodec == "none":
            continue
        bucket = _resolve_bucket_height(fmt)
        if bucket in settings.STANDARD_VIDEO_HEIGHTS:
            size = fmt.get("filesize") or fmt.get("filesize_approx")
            prev = found_buckets.get(bucket)
            if isinstance(size, int) and size > 0:
                if prev is None or size > prev:
                    found_buckets[bucket] = size
            elif bucket not in found_buckets:
                found_buckets[bucket] = None

    options: list[QualityOption] = [
        QualityOption(value="best", label="Terbaik otomatis", height=None, filesize_approx=None)
    ]

    for height in sorted(found_buckets.keys(), reverse=True):
        options.append(
            QualityOption(
                value=str(height),
                label=quality_labels.get(height, f"{height}p"),
                height=height,
                filesize_approx=found_buckets[height],
            )
        )

    return options


def extract_video_info(raw_url: str) -> VideoInfoResponse:
    """
    Mengambil metadata video dan daftar kualitas dari yt-dlp tanpa mengunduh file.
    Dijalankan di worker thread agar tidak memblokir event loop.
    """
    clean_url, platform = validate_and_identify_url(raw_url)
    opts = _base_ytdlp_opts()
    opts["extract_flat"] = False

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
    except Exception as exc:
        raise map_ytdlp_error(exc) from exc

    if not info:
        raise DownloaderUserError("Tidak dapat mengambil informasi dari tautan tersebut.", status_code=404)

    # Jika URL mengarah ke post multi-item (carousel/playlist), ambil entri pertama
    if "entries" in info and isinstance(info["entries"], list):
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise DownloaderUserError("Postingan tersebut tidak memuat video yang dapat diunduh.", status_code=404)
        info = entries[0]

    if info.get("is_live"):
        raise DownloaderUserError(
            "Siaran langsung (live stream) yang sedang berlangsung tidak didukung.",
            status_code=400,
        )

    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > settings.MAX_DURATION_SECONDS:
        max_min = settings.MAX_DURATION_MINUTES
        actual_min = int(round(duration / 60))
        raise DownloaderUserError(
            f"Durasi video ({actual_min} menit) melebihi batas maksimum yang diizinkan ({max_min} menit).",
            status_code=400,
        )

    formats = info.get("formats") or []
    video_qualities = _build_quality_options(formats)

    title = (info.get("title") or info.get("fulltitle") or f"Video {platform}").strip()
    uploader = (
        info.get("uploader")
        or info.get("channel")
        or info.get("creator")
        or info.get("uploader_id")
        or platform
    )
    thumbnail = info.get("thumbnail")
    if not thumbnail and isinstance(info.get("thumbnails"), list) and info["thumbnails"]:
        thumbnail = info["thumbnails"][-1].get("url")

    duration_int = int(round(duration)) if isinstance(duration, (int, float)) and duration > 0 else None

    return VideoInfoResponse(
        title=title,
        uploader=str(uploader),
        duration=duration_int,
        duration_string=format_duration(duration_int),
        thumbnail=thumbnail,
        platform=platform,
        webpage_url=info.get("webpage_url") or clean_url,
        video_qualities=video_qualities,
        audio_bitrates=list(settings.ALLOWED_AUDIO_BITRATES),
    )


@dataclass
class DownloadedMedia:
    file_path: Path
    temp_dir: Path
    download_filename: str
    media_type: str


def _build_video_format_selector(quality: str) -> str:
    """
    Membuat format selector yt-dlp yang memprioritaskan codec H.264 (avc1) + AAC (mp4a)
    agar file MP4 kompatibel di semua perangkat (iOS, Android, Windows, macOS, Smart TV),
    serta mendukung video lanskap maupun vertikal (Shorts/Reels/TikTok).
    """
    if quality != "best" and quality.isdigit():
        target = int(quality)
        dim_filter = f"[height<={target}]"
        v_dim_filter = f"[width<={target}]"
        return (
            f"bestvideo{dim_filter}[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            f"bestvideo{v_dim_filter}[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            f"bestvideo{dim_filter}+bestaudio/"
            f"bestvideo{v_dim_filter}+bestaudio/"
            f"best{dim_filter}/best{v_dim_filter}/best"
        )

    return (
        "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
        "bestvideo+bestaudio/"
        "best"
    )


def download_media(
    raw_url: str,
    format_type: str,
    quality: str,
    task_id: Optional[str] = None,
) -> DownloadedMedia:
    """
    Mengunduh dan memproses video (MP4) atau audio (MP3) ke folder sementara unik.
    Memastikan kompatibilitas perangkat penuh dan penyematan metadata/cover MP3.
    """
    if not is_ffmpeg_available():
        raise DownloaderUserError(
            "FFmpeg tidak ditemukan di sistem. Silakan instal FFmpeg terlebih dahulu agar Forte dapat memproses video dan MP3.",
            status_code=500,
        )

    clean_url, platform = validate_and_identify_url(raw_url)

    if format_type == "audio":
        bitrate = int(quality) if quality.isdigit() and int(quality) in settings.ALLOWED_AUDIO_BITRATES else 192
    else:
        if quality != "best" and (not quality.isdigit() or int(quality) not in settings.STANDARD_VIDEO_HEIGHTS):
            quality = "best"
        bitrate = 192

    job_dir = settings.TEMP_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    progress_tracker.update(task_id, "Inspecting", 5.0, "Memeriksa informasi media...")

    def _progress_hook(d: dict[str, Any]) -> None:
        status_val = d.get("status")
        if status_val == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

            if downloaded > settings.MAX_FILE_SIZE_BYTES or total > settings.MAX_FILE_SIZE_BYTES:
                raise DownloaderUserError(
                    f"Ukuran file melebihi batas maksimum ({settings.MAX_FILE_SIZE_MB} MB).",
                    status_code=413,
                )

            if total > 0:
                pct = 10.0 + (downloaded / total) * 75.0
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                progress_tracker.update(
                    task_id,
                    "downloading",
                    pct,
                    f"Mengunduh media... {int((downloaded / total) * 100)}% ({mb_done:.1f} / {mb_total:.1f} MB)",
                )
            else:
                mb_done = downloaded / (1024 * 1024)
                progress_tracker.update(
                    task_id,
                    "downloading",
                    45.0,
                    f"Mengunduh media... ({mb_done:.1f} MB)",
                )
        elif status_val == "finished":
            progress_tracker.update(
                task_id,
                "processing",
                88.0,
                "Menggabungkan & mengoptimalkan file dengan FFmpeg...",
            )

    def _run_ydl(embed_thumb: bool = True) -> dict[str, Any]:
        opts = _base_ytdlp_opts()
        opts["outtmpl"] = str(job_dir / "media.%(ext)s")
        opts["max_filesize"] = settings.MAX_FILE_SIZE_BYTES
        opts["progress_hooks"] = [_progress_hook]

        if format_type == "audio":
            opts["format"] = "bestaudio/best"
            postprocessors: list[dict[str, Any]] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate),
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
            ]
            if embed_thumb:
                opts["writethumbnail"] = True
                postprocessors.insert(
                    1,
                    {
                        "key": "FFmpegThumbnailsConvertor",
                        "format": "jpg",
                    },
                )
                postprocessors.append({"key": "EmbedThumbnail"})
            opts["postprocessors"] = postprocessors
        else:
            opts["format"] = _build_video_format_selector(quality)
            opts["merge_output_format"] = "mp4"
            # Pastikan audio di dalam MP4 dikonversi ke AAC dan header moov di awal (+faststart)
            # agar dapat diputar di iPhone/iPad, Android, Windows, macOS, dan Smart TV
            opts["postprocessor_args"] = {
                "merger": ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
            }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise DownloaderUserError("Media tidak ditemukan.", status_code=404)

            if "entries" in info and isinstance(info["entries"], list):
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise DownloaderUserError("Postingan tidak memuat media.", status_code=404)
                info = entries[0]

            if info.get("is_live"):
                raise DownloaderUserError(
                    "Siaran langsung (live stream) tidak didukung.",
                    status_code=400,
                )

            duration = info.get("duration")
            if isinstance(duration, (int, float)) and duration > settings.MAX_DURATION_SECONDS:
                raise DownloaderUserError(
                    f"Durasi video melebihi batas maksimum ({settings.MAX_DURATION_MINUTES} menit).",
                    status_code=400,
                )

            progress_tracker.update(task_id, "downloading", 12.0, "Memulai pengunduhan...")
            ydl.download([info.get("webpage_url") or clean_url])
            return info

    try:
        try:
            info_dict = _run_ydl(embed_thumb=(format_type == "audio"))
        except (DownloadError, ExtractorError, Exception) as first_err:
            # Jika pengunduhan MP3 gagal hanya karena thumbnail gagal diunduh/di-embed,
            # ulangi tanpa thumbnail agar pengguna tetap mendapatkan file MP3 dengan metadata
            if format_type == "audio" and "thumbnail" in str(first_err).lower():
                logger.info("Gagal menyematkan thumbnail MP3, mengulangi konversi tanpa thumbnail.")
                for leftover in job_dir.iterdir():
                    leftover.unlink(missing_ok=True)
                info_dict = _run_ydl(embed_thumb=False)
            else:
                raise first_err

        target_ext = "mp3" if format_type == "audio" else "mp4"
        expected_file = job_dir / f"media.{target_ext}"

        if not expected_file.is_file():
            # Cari file hasil konversi di dalam job_dir
            candidates = [
                p for p in job_dir.iterdir()
                if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".jpg", ".webp", ".png", ".json")
            ]
            if not candidates:
                raise DownloaderUserError("Gagal menghasilkan file media. Silakan coba kualitas lain.", status_code=500)
            expected_file = max(candidates, key=lambda p: p.stat().st_size)

        file_size = expected_file.stat().st_size
        if file_size > settings.MAX_FILE_SIZE_BYTES:
            raise DownloaderUserError(
                f"Ukuran file hasil unduhan melebihi batas maksimum ({settings.MAX_FILE_SIZE_MB} MB).",
                status_code=413,
            )

        title = (info_dict.get("title") or info_dict.get("fulltitle") or f"Forte {platform}").strip()
        final_ext = expected_file.suffix.lstrip(".") or target_ext
        clean_filename = sanitize_filename(title, final_ext)
        media_type = "audio/mpeg" if final_ext == "mp3" else "video/mp4"

        progress_tracker.update(task_id, "completed", 100.0, "Unduhan selesai! Mengirim file ke browser...")

        return DownloadedMedia(
            file_path=expected_file,
            temp_dir=job_dir,
            download_filename=clean_filename,
            media_type=media_type,
        )

    except Exception as exc:
        remove_temp_dir(job_dir)
        user_err = map_ytdlp_error(exc)
        progress_tracker.update(task_id, "error", 0.0, user_err.message)
        raise user_err from exc


def remove_temp_dir(folder_path: Path) -> None:
    """Menghapus folder sementara permintaan setelah file dikirim ke pengguna."""
    try:
        if folder_path.exists() and folder_path.is_dir():
            shutil.rmtree(folder_path, ignore_errors=True)
    except Exception as exc:
        logger.warning("Gagal menghapus folder sementara %s: %s", folder_path.name, exc)


def cleanup_expired_temp_dirs() -> int:
    """
    Menghapus semua subfolder di dalam TEMP_DIR yang berumur lebih dari CLEANUP_MAX_AGE_SECONDS.
    Mengembalikan jumlah folder yang dibersihkan.
    """
    removed_count = 0
    now = time.time()
    max_age = settings.CLEANUP_MAX_AGE_SECONDS

    if not settings.TEMP_DIR.exists():
        return 0

    for item in settings.TEMP_DIR.iterdir():
        try:
            age = now - item.stat().st_mtime
            if age >= max_age:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                removed_count += 1
        except Exception as exc:
            logger.warning("Gagal memeriksa/menghapus item sementara %s: %s", item.name, exc)

    progress_tracker.cleanup_old(max_age)
    if removed_count > 0:
        logger.info("Pembersihan berkala menghapus %d folder/file sementara kedaluwarsa.", removed_count)
    return removed_count

