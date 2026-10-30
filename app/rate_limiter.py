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
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                raw_ip = str(forwarded).split(",")[0].strip()
            elif headers.get("x-real-ip"):
                raw_ip = str(headers.get("x-real-ip")).strip()

        if not raw_ip:
            client = getattr(req, "client", None)
            if client and getattr(client, "host", None):
                raw_ip = str(client.host).strip()

        if not raw_ip:
            return "unknown"

        cleaned = raw_ip.strip()
        if not cleaned:
            return "unknown"

        if len(cleaned) > 64:
            cleaned = cleaned[:64]

        return cleaned

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

