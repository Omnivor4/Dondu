import re
import unicodedata
from urllib.parse import quote, urlparse


PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "TikTok": (
        "tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    ),
    "Instagram": (
        "instagram.com",
        "instagr.am",
        "ddinstagram.com",
    ),
    "Facebook": (
        "facebook.com",
        "fb.watch",
        "fb.com",
    ),
    "X": (
        "x.com",
        "twitter.com",
        "t.co",
        "fxtwitter.com",
        "vxtwitter.com",
    ),
    "YouTube": (
        "youtube.com",
        "youtu.be",
        "youtube-nocookie.com",
    ),
}


class URLValidationError(ValueError):
    """Dilempar ketika URL tidak valid atau berasal dari domain yang tidak didukung."""


def validate_and_identify_url(raw_url: str) -> tuple[str, str]:
    """
    Memvalidasi URL dan mengembalikan tuple (cleaned_url, platform_name).
    Melempar URLValidationError dengan pesan bahasa Indonesia jika tidak valid.
    """
    if not raw_url or not raw_url.strip():
        raise URLValidationError("Silakan masukkan tautan (URL) video terlebih dahulu.")

    url = raw_url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise URLValidationError(
            "Format tautan tidak valid. Pastikan tautan diawali dengan http:// atau https://."
        )

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise URLValidationError("Format tautan tidak dapat dikenali. Periksa kembali URL Anda.") from exc

    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        raise URLValidationError("Tautan tidak memiliki nama domain yang valid.")

    for platform, allowed_roots in PLATFORM_DOMAINS.items():
        for root in allowed_roots:
            if hostname == root or hostname.endswith("." + root):
                if parsed.path in ("", "/") and not parsed.query:
                    raise URLValidationError(
                        f"Tautan {platform} belum lengkap. Masukkan tautan langsung ke postingan atau video."
                    )
                return url, platform

    supported_list = "TikTok, Instagram, Facebook, X (Twitter), dan YouTube"
    raise URLValidationError(
        f"Domain '{hostname}' tidak didukung. Forte hanya mendukung tautan dari {supported_list}."
    )


def sanitize_filename(title: str, extension: str) -> str:
    """
    Membersihkan judul video menjadi nama file yang aman di Windows, macOS, Linux, Android, dan iOS.
    """
    ext = extension.lstrip(".").lower() or "mp4"
    if not title:
        return f"Forte_Media.{ext}"

    # Normalisasi karakter Unicode
    cleaned = unicodedata.normalize("NFKC", title)
    # Hapus karakter ilegal sistem file dan karakter kontrol
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', " ", cleaned)
    # Ganti spasi beruntun dengan satu spasi
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-\t\r\n")

    # Batasi panjang judul agar tidak melampaui batas path OS
    if len(cleaned) > 140:
        cleaned = cleaned[:140].rstrip(" ._-")

    if not cleaned:
        cleaned = "Forte_Media"

    return f"{cleaned}.{ext}"


def build_content_disposition(filename: str) -> str:
    """
    Membuat header Content-Disposition yang kompatibel dengan semua browser modern (ASCII + UTF-8 RFC 5987).
    """
    ascii_fallback = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_fallback = re.sub(r'["\\]', "", ascii_fallback).strip()
    if not ascii_fallback or ascii_fallback.startswith("."):
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
        ascii_fallback = f"Forte_Media.{ext}"

    utf8_quoted = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{utf8_quoted}'

