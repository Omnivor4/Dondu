import ipaddress
import re
import socket
import unicodedata
from typing import Optional
from urllib.parse import quote, urlparse

from app.config import settings


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

TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class URLValidationError(ValueError):
    """Dilempar ketika URL tidak valid atau berasal dari domain yang tidak didukung."""


def is_forbidden_host_or_ip(hostname: str, resolve_dns: bool = False) -> bool:
    """
    Memeriksa apakah hostname atau IP address terlarang (SSRF protection):
    - localhost atau domain internal (.local, .internal, .arpa, .localhost)
    - Alamat IP privat, loopback, link-local, multicast, reserved, unspecified
    - Opsional: resolusi DNS aktif untuk memeriksa IP di balik hostname
    """
    if not hostname:
        return True

    host = hostname.lower().strip(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    # Selalu blokir localhost dan domain internal
    if host == "localhost" or host.endswith((".local", ".internal", ".arpa", ".localhost")):
        return True

    def _is_ip_forbidden(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if getattr(ip_obj, "ipv4_mapped", None) is not None:
            ip_obj = ip_obj.ipv4_mapped
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )

    # Cek jika literal IP
    try:
        ip = ipaddress.ip_address(host)
        return _is_ip_forbidden(ip)
    except ValueError:
        pass

    # Opsional: resolusi DNS aktif
    if resolve_dns:
        try:
            addr_info = socket.getaddrinfo(host, None)
            for entry in addr_info:
                ip_str = entry[4][0]
                try:
                    resolved_ip = ipaddress.ip_address(ip_str)
                    if _is_ip_forbidden(resolved_ip):
                        return True
                except ValueError:
                    continue
        except (socket.gaierror, OSError):
            pass

    return False


def validate_task_id(task_id: Optional[str]) -> Optional[str]:
    """
    Memvalidasi format task_id.
    Mengembalikan None jika task_id bernilai None atau string kosong.
    Mengembalikan task_id jika valid sesuai pola alphanumerik, underscore, dan hyphen (1-64 karakter).
    Melempar URLValidationError jika format tidak valid.
    """
    if task_id is None or task_id == "":
        return None

    if not isinstance(task_id, str) or not TASK_ID_PATTERN.match(task_id):
        raise URLValidationError("Format ID tugas (task_id) tidak valid.")

    return task_id


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

    try:
        has_credentials = bool(parsed.username or parsed.password)
    except ValueError as exc:
        raise URLValidationError("Tautan tidak boleh memuat kredensial autentikasi.") from exc

    if has_credentials:
        raise URLValidationError("Tautan tidak boleh memuat kredensial autentikasi.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise URLValidationError("Port pada tautan tidak diizinkan. Gunakan port standar HTTP/HTTPS.") from exc

    if port not in (None, 80, 443):
        raise URLValidationError("Port pada tautan tidak diizinkan. Gunakan port standar HTTP/HTTPS.")

    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        raise URLValidationError("Tautan tidak memiliki nama domain yang valid.")

    if is_forbidden_host_or_ip(hostname, resolve_dns=settings.RESOLVE_DNS_SSRF_CHECK):
        raise URLValidationError("Tautan menuju alamat jaringan internal atau lokal tidak diizinkan.")

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
