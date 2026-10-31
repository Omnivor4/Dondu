import ipaddress
import math
import time
from collections import deque
from threading import Lock
from typing import Any, Optional
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """
    Rate limiter berbasis sliding window per alamat IP di memori.
    Aman untuk multi-thread dan membersihkan entri kedaluwarsa secara berkala.
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        trust_proxy_headers: bool = False,
        max_tracked_ips: int = 10000,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.trust_proxy_headers = trust_proxy_headers
        self.max_tracked_ips = max_tracked_ips
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_gc = time.monotonic()

    def get_client_ip(self, request: Any = None) -> str:
        # Dukung pemanggilan sebagai method instance (self.get_client_ip(request))
        # maupun pemanggilan secara static (SlidingWindowRateLimiter.get_client_ip(request))
        if isinstance(self, SlidingWindowRateLimiter):
            req = request
            trust = self.trust_proxy_headers
        else:
            req = self
            trust = False

        if req is None:
            return "unknown"

        raw_ip: Optional[str] = None
        headers = getattr(req, "headers", {}) or {}

        if trust:
            # Prioritaskan x-vercel-forwarded-for atau x-forwarded-for.
            # Pada reverse proxy (Vercel/Nginx/Cloudflare), IP client yang dapat dipercaya
            # ditambahkan di posisi paling kanan (rightmost) oleh proxy terdekat.
            forwarded = headers.get("x-vercel-forwarded-for") or headers.get("x-forwarded-for")
            if forwarded:
                raw_ip = str(forwarded).split(",")[-1].strip()
            elif headers.get("x-real-ip"):
                raw_ip = str(headers.get("x-real-ip")).strip()

        # Fallback ke socket client langsung jika header proxy tidak ada atau trust=False
        if not raw_ip:
            client = getattr(req, "client", None)
            if client and getattr(client, "host", None):
                raw_ip = str(client.host).strip()

        if not raw_ip:
            return "unknown"

        cleaned = raw_ip.strip()
        if not cleaned:
            return "unknown"

        # Tangani notasi IPv6 dengan kurung [::1] atau port IPv4 (1.2.3.4:8080)
        if cleaned.startswith("[") and "]" in cleaned:
            cleaned = cleaned.split("]")[0].lstrip("[")
        elif cleaned.count(":") == 1:
            cleaned = cleaned.split(":")[0]

        # Validasi sintaks IP untuk mencegah pemalsuan string non-IP dan polusi memori
        try:
            ip_obj = ipaddress.ip_address(cleaned)
            return str(ip_obj)
        except ValueError:
            # Jika IP dari proxy tidak valid secara sintaks, fallback ke host TCP client langsung
            client = getattr(req, "client", None)
            if client and getattr(client, "host", None):
                fallback_host = str(client.host).strip()
                if fallback_host == "testclient":
                    return "testclient"
                try:
                    ip_obj = ipaddress.ip_address(fallback_host)
                    return str(ip_obj)
                except ValueError:
                    pass
            if cleaned == "testclient":
                return "testclient"
            return "unknown"

    def check(self, request: Request) -> None:
        now = time.monotonic()
        client_ip = self.get_client_ip(request)
        cutoff = now - self.window_seconds

        with self._lock:
            # Bersihkan IP tidak aktif setiap 5 menit agar memori tetap ringan
            if now - self._last_gc > 300:
                expired_ips = [
                    ip for ip, timestamps in self._hits.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for ip in expired_ips:
                    self._hits.pop(ip, None)
                self._last_gc = now

            # Batasi memori: evict entri tertua jika kapasitas maksimum tercapai
            if client_ip not in self._hits and len(self._hits) >= self.max_tracked_ips:
                if self._hits:
                    oldest_ip = next(iter(self._hits))
                    self._hits.pop(oldest_ip, None)

            bucket = self._hits.get(client_ip)
            if bucket is None:
                bucket = deque()
                self._hits[client_ip] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, math.ceil(self.window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Terlalu banyak permintaan dari koneksi Anda (maksimal {self.max_requests} permintaan/menit). "
                        f"Silakan tunggu {retry_after} detik sebelum mencoba kembali."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)

