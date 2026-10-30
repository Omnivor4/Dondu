# Forte Security Audit, Vulnerability Remediation & Production Hardening Plan

## Spec & Global Constraints
- **R1. Code and Architecture Audit with Improvement Report**: Conduct a comprehensive audit of the application codebase, dependencies, and deployment configuration. Deliver a structured audit report (`AUDIT_REPORT.md`) detailing findings, remediated vulnerabilities, and actionable suggestions for code quality, architectural improvements, and deployment readiness.
- **R2. Security Vulnerability Remediation**: Identify and directly fix all security vulnerabilities across the codebase, dependencies, and configuration without breaking existing functionality:
  1. **SSRF & Open Redirect Protection (`app/validators.py`, `app/downloader.py`)**:
     - Reject URLs containing embedded credentials (`username` or `password`) or non-standard ports (only `None`, `80`, `443` allowed).
     - Validate that resolved IP addresses (when DNS resolution is enabled/available) or literal IP hostnames are never loopback, private, link-local, multicast, or reserved (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, etc.).
     - Re-validate `info.get("webpage_url")` after `yt-dlp` metadata extraction in both `extract_video_info` and `download_media` so shortlinks (`t.co`, `vm.tiktok.com`, `fb.watch`, `youtu.be`) cannot redirect to non-allowlisted domains or internal services.
     - Restrict `yt-dlp` options with `"allowed_protocols": ["http", "https"]` and `"max_downloads": 1`.
  2. **Rate Limiter Spoofing & Memory Exhaustion Protection (`app/rate_limiter.py`, `app/config.py`)**:
     - Do not trust `X-Forwarded-For` or `X-Real-IP` headers unless `TRUST_PROXY_HEADERS=true` is explicitly configured in environment variables (`settings.TRUST_PROXY_HEADERS`, default `False`).
     - Cap tracked IP buckets (`max_tracked_ips=10000`) in `SlidingWindowRateLimiter` with oldest-entry eviction to prevent memory exhaustion DoS.
     - Cap `ProgressTracker` entries (`max_entries=2000`) and validate `task_id` against `^[a-zA-Z0-9_-]{1,64}$`.
  3. **Concurrency & Resource Exhaustion Protection (`app/main.py`, `app/config.py`)**:
     - Enforce `asyncio.Semaphore` limits for concurrent info checks (`MAX_CONCURRENT_INFO=8`) and concurrent media downloads (`MAX_CONCURRENT_DOWNLOADS=3`) with a fast acquisition timeout, returning HTTP 503 with a friendly Indonesian message when saturated.
     - Add a dedicated rate limiter (`120/min` per IP) and strict regex validation on `GET /api/progress/{task_id}`.
  4. **HTTP Security Headers, Frontend XSS Protection & Container Hardening (`app/main.py`, `static/app.js`, `Dockerfile`)**:
     - Add HTTP security headers middleware (`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`).
     - Disable `/docs` and `/openapi.json` by default in production (`ENABLE_DOCS=false` by default in `settings`).
     - Sanitize thumbnail URLs in both backend (`extract_video_info`) and frontend (`static/app.js`) to only allow `https://` or `http://` URLs.
     - Harden `Dockerfile` to run as an unprivileged user (`forte`, UID `10001`), use `chmod 700 /tmp/forte_downloads`, and avoid running `uvicorn` as `root`.

---

## Task 1: URL Validator SSRF Hardening & Configuration Updates
- **Files**: `app/config.py`, `app/validators.py`, `app/schemas.py`, `tests/test_validators.py`
- **Requirements**:
  1. In `app/config.py`, add:
     - `TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")`
     - `ENABLE_DOCS: bool = os.getenv("ENABLE_DOCS", "false").lower() in ("1", "true", "yes")`
     - `MAX_CONCURRENT_INFO: int = int(os.getenv("MAX_CONCURRENT_INFO", "8"))`
     - `MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))`
  2. In `app/validators.py`:
     - Reject URLs with `parsed.username` or `parsed.password`.
     - Reject URLs with `parsed.port not in (None, 80, 443)`.
     - Reject literal IP addresses or hostnames resolving to private/loopback/link-local/reserved IP addresses via helper `is_Blocked_ip(host)`.
     - Add `validate_task_id(task_id: Optional[str]) -> Optional[str]` that validates `^[a-zA-Z0-9_-]{1,64}$` and raises `URLValidationError("ID tugas (task_id) tidak valid.")` if invalid.
  3. In `app/schemas.py`:
     - Add a Pydantic field validator on `DownloadRequest.task_id` using `validate_task_id`.
  4. Create `tests/test_validators.py` with `unittest` covering allowlisted domains, rejected domains, embedded credentials, non-standard ports, private/loopback IPs, `sanitize_filename`, `build_content_disposition`, and `validate_task_id`.

## Task 2: Rate Limiter, Progress Tracker & Downloader Security Hardening
- **Files**: `app/rate_limiter.py`, `app/downloader.py`, `tests/test_security_backend.py`
- **Requirements**:
  1. In `app/rate_limiter.py`:
     - Update `SlidingWindowRateLimiter.__init__` to accept `trust_proxy_headers: bool = False` and `max_tracked_ips: int = 10000`.
     - Only read `x-forwarded-for` / `x-real-ip` when `self.trust_proxy_headers` is `True` and validate that the extracted candidate IP is a non-empty string up to 64 chars.
     - When `len(self._hits) >= self.max_tracked_ips` and a new IP arrives, evict the oldest key (`next(iter(self._hits))`) so memory cannot grow unbounded.
  2. In `app/downloader.py`:
     - Cap `ProgressTracker._store` at `max_entries: int = 2000` (evicting the oldest key when full).
     - Add `"allowed_protocols": ["http", "https"]` and `"max_downloads": 1` to `_base_ytdlp_opts()`.
     - Add `_sanitize_thumbnail_url(url: Optional[str]) -> Optional[str]` that only permits `http://` or `https://` URLs up to 2048 chars, returning `None` for `javascript:`, `data:`, `file:`, or malformed URLs.
     - In both `extract_video_info` and `download_media`, after `ydl.extract_info(clean_url, download=False)` resolves `info`, if `info.get("webpage_url")` is present, validate it with `validate_and_identify_url(info["webpage_url"])` so shortlinks (`t.co`, `vm.tiktok.com`, etc.) redirecting to disallowed domains or internal hosts are blocked immediately!
  3. Create `tests/test_security_backend.py` with `unittest` verifying rate limiter proxy header behavior, max tracked IP eviction, progress tracker bounding, thumbnail URL sanitization, and post-redirect `webpage_url` validation.

## Task 3: API Security Middleware, Concurrency Semaphores, Frontend & Docker Hardening
- **Files**: `app/main.py`, `static/app.js`, `Dockerfile`, `.env.example`, `tests/test_api_hardening.py`
- **Requirements**:
  1. In `app/main.py`:
     - Configure `docs_url="/docs" if settings.ENABLE_DOCS else None` and `openapi_url="/openapi.json" if settings.ENABLE_DOCS else None`.
     - Pass `trust_proxy_headers=settings.TRUST_PROXY_HEADERS` to `rate_limiter`, and create `progress_rate_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60, trust_proxy_headers=settings.TRUST_PROXY_HEADERS)`.
     - Add HTTP security headers middleware on all responses:
       - `X-Content-Type-Options: nosniff`
       - `X-Frame-Options: DENY`
       - `Referrer-Policy: no-referrer`
       - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
       - `Content-Security-Policy: default-src 'self'; img-src 'self' https: http: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
     - Add `info_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFO)` and `download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)`. Acquire with `asyncio.wait_for(..., timeout=2.0)` in `/api/info` and `/api/download`; if timeout occurs, return HTTP 503 with message `"Server sedang sibuk memproses banyak permintaan. Silakan coba lagi beberapa detik."`.
     - Validate `task_id` in `GET /api/progress/{task_id}` via `validate_task_id(task_id)` and check `progress_rate_limiter.check(request)`.
     - In `GET /health`, remove `yt_dlp_version` to avoid version fingerprinting in production (keep `status`, `app`, `version`, `ffmpeg_installed`, `limits`).
  2. In `static/app.js`:
     - Add `isSafeHttpUrl(url)` check before setting `previewThumbnail.src` so only `https://` or `http://` URLs are assigned to `previewThumbnail.src`.
  3. In `Dockerfile` and `.env.example`:
     - Update `Dockerfile` to create non-root user `forte` (UID 10001), set `chown -R forte:forte /app /tmp/forte_downloads`, `chmod 700 /tmp/forte_downloads`, switch to `USER forte`, and run `uvicorn` with `--no-access-log --timeout-keep-alive 30`.
     - Update `.env.example` with `TRUST_PROXY_HEADERS`, `ENABLE_DOCS`, `MAX_CONCURRENT_INFO`, and `MAX_CONCURRENT_DOWNLOADS`.
  4. Create `tests/test_api_hardening.py` testing security headers, `/health`, `/api/progress/{task_id}` validation, `/docs` disabled by default, and `/api/info` invalid URL handling.

## Task 4: Comprehensive Audit Report (`AUDIT_REPORT.md`) & Documentation Update (`README.md`)
- **Files**: `AUDIT_REPORT.md`, `README.md`
- **Requirements**:
  1. Write a thorough, production-grade audit report in `AUDIT_REPORT.md` covering:
     - Executive Summary
     - Remediated Security Vulnerabilities (Severity, Location, Risk, Fix Applied)
     - Architecture, Performance & Scalability Recommendations for Production Deployment (Reverse Proxy/Nginx/Cloudflare setup, Redis-backed rate limiting for multi-worker scaling, Egress IP rotation/cookies handling, Disk quota tmpfs mounting, Observability)
     - Pre-Deployment Checklist
  2. Update `README.md` to document the new security environment variables (`TRUST_PROXY_HEADERS`, `ENABLE_DOCS`, `MAX_CONCURRENT_INFO`, `MAX_CONCURRENT_DOWNLOADS`) and how to run the automated test suite (`python -m unittest discover -s tests -v`).
