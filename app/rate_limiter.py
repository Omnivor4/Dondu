import math
import time
from collections import deque
from threading import Lock
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """
    Rate limiter berbasis sliding window per alamat IP di memori.
    Aman untuk multi-thread dan membersihkan entri kedaluwarsa secara berkala.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_gc = time.monotonic()

    @staticmethod
    def get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
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

