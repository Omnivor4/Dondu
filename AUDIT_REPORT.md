# Laporan Audit Keamanan & Arsitektur Aplikasi Dondu

**Versi Dokumen**: 1.0  
**Tanggal Audit**: 30 Oktober 2026  
**Status Audit**: Selesai & Terverifikasi (41/41 Automated Unit Tests Lolos)  
**Target Aplikasi**: Dondu (FastAPI + yt-dlp + FFmpeg Video/Audio Downloader)

---

## 1. Ringkasan Eksekutif (Executive Summary)

Audit keamanan menyeluruh dan penguatan arsitektur (*hardening*) telah dilakukan terhadap aplikasi **Dondu**. Dondu dirancang sebagai layanan web mandiri (*self-hosted*) untuk mengunduh video dan audio dari platform publik terkemuka (TikTok, Instagram, Facebook, X/Twitter, dan YouTube). Mengingat sifat alami aplikasi pengunduh media yang berinteraksi langsung dengan URL eksternal, mengeksekusi subproses *transcoding*, dan mengelola file sementara di disk, aplikasi ini memiliki bidang serangan (*attack surface*) yang signifikan apabila tidak diproteksi secara ketat.

Audit ini berfokus pada identifikasi, mitigasi, dan verifikasi terhadap lima kategori risiko utama:
1. **Penyalahgunaan Permintaan Server (Server-Side Request Forgery - SSRF) & Open Redirect**: Potensi eksfiltrasi metadata cloud dan pemindaian jaringan internal organisasi.
2. **Manipulasi Pembatas Laju (Rate Limiter Bypass) & Eksploitasi Memori**: Pemalsuan identitas klien melalui header proxy dan penipisan memori (*memory exhaustion*).
3. **Penolakan Layanan (Denial of Service - DoS) & Penipisan Sumber Daya Komputasi**: Beban komputasi ekstrim dari proses FFmpeg dan ekstraksi metadata tanpa pembatas konkurensi.
4. **Isolasi Lingkungan Container Docker**: Menghilangkan risiko eskalasi hak akses (*privilege escalation*) akibat container yang berjalan sebagai `root` dan izin direktori yang terlalu terbuka (`777`).
5. **Keamanan Lapisan Presentasi & API (Web Security Hygiene)**: Injeksi skema URL pada thumbnail, ketiadaan header proteksi HTTP (CSP, X-Frame-Options, dll.), dan kebocoran informasi melalui dokumentasi publik Swagger/OpenAPI.

Seluruh kerentanan yang teridentifikasi telah diremediasi secara tuntas pada kode sumber, konfigurasi Docker, dan middleware aplikasi. Selain itu, kebijakan batas durasi dan ukuran file kini diatur menjadi **tanpa batas (`0 = unlimited`) secara default**, dengan perlindungan stabilitas sistem yang dialihkan ke mekanisme pembatasan konkurensi berbasis semafor (*concurrency semaphore*), rate limiter berbasis memori terbatas, dan isolasi memori sementara (*tmpfs*).

Sebanyak **41 pengujian unit dan integrasi otomatis** telah diimplementasikan dan diverifikasi lulus 100%, memastikan bahwa aplikasi Dondu siap untuk di-*deploy* ke lingkungan produksi dengan tingkat ketahanan yang tinggi.

---

## 2. Rincian Kerentanan yang Ditemukan & Telah Diperbaiki

Berikut adalah rincian teknis dari kerentanan keamanan yang ditemukan pada kode awal beserta solusi perbaikan yang telah diimplementasikan:

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                          RINGKASAN STATUS KERENTANAN                            â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚ ID    â”‚ Severity â”‚ Nama Kerentanan                                 â”‚ Status     â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚ SEC-1 â”‚ CRITICAL â”‚ SSRF & Open Redirect via Shortlink & Validasi   â”‚ REMEDIATED â”‚
â”‚ SEC-2 â”‚ HIGH     â”‚ Rate Limiter Bypass & Memory Exhaustion Header  â”‚ REMEDIATED â”‚
â”‚ SEC-3 â”‚ HIGH     â”‚ Resource Exhaustion via FFmpeg/yt-dlp           â”‚ REMEDIATED â”‚
â”‚ SEC-4 â”‚ HIGH     â”‚ Container Berjalan sebagai Root & chmod 777     â”‚ REMEDIATED â”‚
â”‚ SEC-5 â”‚ MEDIUM   â”‚ Thumbnail Scheme Injection & Header Keamanan    â”‚ REMEDIATED â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

### 2.1 [CRITICAL] SSRF & Open Redirect via Shortlink (`t.co`, `vm.tiktok.com`, dll.) & Validasi URL

#### Deskripsi Celah & Vektor Serangan Awal
Aplikasi mengizinkan domain pemendek tautan resmi seperti `t.co`, `vm.tiktok.com`, `vt.tiktok.com`, `fb.watch`, dan `youtu.be`. Pada implementasi awal:
1. Validasi URL hanya dilakukan pada string URL awal yang dikirimkan oleh pengguna sebelum proses ekstraksi dimulai.
2. Ketika `yt-dlp` memproses URL shortlink, `yt-dlp` secara otomatis mengikuti *HTTP Redirect* (status 301/302). Tautan `t.co` atau `vm.tiktok.com` dapat diarahkan oleh penyerang ke endpoint metadata cloud internal (`http://169.254.169.254/latest/meta-data/`), loopback server lokal (`http://127.0.0.1:8000`), atau subnet privat (`http://192.168.1.1/admin`).
3. URL awal juga tidak memvalidasi keberadaan kredensial tersemat (`http://user:pass@domain.com`) dan port non-standar (`http://domain.com:8080`), yang dapat dimanfaatkan untuk *port scanning* internal.
4. `yt-dlp` secara default mengizinkan berbagai protokol skema URL selain HTTP/HTTPS, seperti `file://`, `ftp://`, atau skema kustom.

#### Dampak Risiko di Produksi
- **Pencurian Kredensial Cloud**: Penyerang pada lingkungan AWS, Google Cloud, atau DigitalOcean dapat mencuri IAM role token, SSH keys, atau secret environment melalui endpoint instance metadata service (`169.254.169.254`).
- **Akses Jaringan Intranet (Pivoting)**: Penyerang dapat mengirimkan payload ke layanan internal yang tidak memiliki autentikasi (seperti Redis lokal, Elasticsearch, atau API microservice privat).

#### Remediasi yang Diterapkan
1. **Validasi Hostname & Blokir IP Terlarang (`app/validators.py`)**:
   - Fungsi `is_forbidden_host_or_ip(hostname, resolve_dns)` memblokir:
     - Hostname internal: `localhost`, serta domain berakhiran `.local`, `.internal`, `.arpa`, dan `.localhost`.
     - Rentang IP terlarang: Alamat privat (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local/cloud metadata (`169.254.0.0/16`, `fe80::/10`), multicast (`224.0.0.0/4`), unspecified (`0.0.0.0`), dan reserved.
     - **Penanganan IPv4-Mapped IPv6**: Memeriksa `if getattr(ip_obj, "ipv4_mapped", None) is not None: ip_obj = ip_obj.ipv4_mapped` sehingga format seperti `::ffff:127.0.0.1` atau `::ffff:169.254.169.254` terdeteksi dan diblokir secara akurat.
     - Opsi `RESOLVE_DNS_SSRF_CHECK`: Jika diaktifkan (`true`), sistem melakukan resolusi DNS aktif untuk memastikan IP publik yang dihasilkan hostname bukan merupakan IP privat.
2. **Pembersihan Kredensial & Pembatasan Port Standar**:
   - URL yang memuat username/password (`parsed.username` atau `parsed.password`) langsung ditolak dengan pesan kesalahan eksplisit.
   - Port dibatasi secara ketat hanya pada port standar HTTP (`80`) dan HTTPS (`443`). Port selain itu langsung ditolak.
3. **Validasi Ulang Pasca-Ekstraksi (Post-Extraction Redirect Guard di `app/downloader.py`)**:
   - Baik pada fungsi `extract_video_info` maupun `download_media`, setelah metadata diekstrak oleh `yt-dlp`, sistem membaca `info.get("webpage_url") or info.get("original_url")`.
   - URL target hasil redirect divalidasi ulang menggunakan `validate_and_identify_url()`. Jika target redirect mengarah ke domain yang tidak terdaftar di whitelist resmi atau mengarah ke IP internal/privat, proses langsung dibatalkan dengan melempar `URLValidationError`.
   - Pada `download_media`, validasi ini dieksekusi **sebelum** fungsi `ydl.download()` dipanggil, memastikan tidak ada satu bita pun data yang diunduh dari target terlarang.
4. **Pembatasan Protokol yt-dlp**:
   - Parameter dasar `_base_ytdlp_opts()` ditambahkan opsi `"allowed_protocols": ["http", "https"]` dan `"max_downloads": 1`.

---

### 2.2 [HIGH] Bypass Rate Limiter & Memory Exhaustion melalui Spoofing Header Proxy

#### Deskripsi Celah & Vektor Serangan Awal
1. Fungsi pembaca alamat IP klien (`get_client_ip`) pada `SlidingWindowRateLimiter` sebelumnya mempercayai header `X-Forwarded-For` dan `X-Real-IP` secara langsung tanpa verifikasi apakah aplikasi berada di balik reverse proxy terpercaya.
2. Penyerang dapat memalsukan IP dengan menyuntikkan header acak pada setiap request (misal `X-Forwarded-For: 1.2.3.4`, `1.2.3.5`, dst.), sehingga kuota rate limit per IP tidak pernah tercapai.
3. Kamus (*dictionary*) pelacak riwayat request (`self._hits`) menyimpan stempel waktu untuk setiap IP unik tanpa batas maksimum ukuran. Penyerang yang mengirimkan jutaan IP acak dapat menyebabkan konsumsi RAM terus melonjak (*unbounded memory leak*) hingga container dimatikan oleh kernel (*Out-Of-Memory / OOM killer*).

#### Dampak Risiko di Produksi
- Penyerang dapat membanjiri server dengan ribuan permintaan cek info dan download per menit (*API flooding / DoS*).
- Server mengalami *crash* akibat kehabisan memori RAM.

#### Remediasi yang Diterapkan
1. **Konfigurasi `TRUST_PROXY_HEADERS` (`app/config.py` & `app/rate_limiter.py`)**:
   - Nilai default diatur ke `false`. Header `X-Forwarded-For` dan `X-Real-IP` diabaikan sepenuhnya, dan sistem hanya menggunakan `request.client.host` dari koneksi TCP langsung.
   - Header proxy hanya dipercaya jika variabel environment `TRUST_PROXY_HEADERS=true` diaktifkan secara sengaja oleh administrator yang menggunakan reverse proxy terkonfigurasi aman.
2. **Sanitasi String IP Klien**:
   - String IP dipangkas dari whitespace, dibatasi maksimal 64 karakter untuk mencegah payload raksasa, dan memiliki fallback ke `"unknown"`.
3. **Pembatasan Batas Kapasitas Memori (Bounded Memory via FIFO Eviction)**:
   - Parameter `max_tracked_ips: int = 10000` ditambahkan pada `SlidingWindowRateLimiter`.
   - Jika jumlah IP yang dilacak mencapai 10.000 dan ada IP baru yang masuk, entri IP paling lama (*oldest entry*) akan langsung dihapus (*FIFO eviction*) menggunakan `self._hits.pop(next(iter(self._hits)), None)`.

---

### 2.3 [HIGH] Resource Exhaustion & DoS akibat Proses FFmpeg & yt-dlp Tanpa Batas Konkurensi

#### Deskripsi Celah & Vektor Serangan Awal
1. Operasi ekstraksi informasi media (`yt-dlp`) dan konversi media (penggabungan video/audio dan transcode MP3 oleh `FFmpeg`) merupakan operasi yang sangat membebani CPU, RAM, dan Disk I/O.
2. Tanpa mekanisme pembatas konkurensi (*concurrency throttle*), beberapa pengguna yang meminta unduhan file besar atau video 4K secara bersamaan dapat memicu puluhan subproses FFmpeg simultan.
3. Kamus `ProgressTracker` menyimpan status unduhan berdasarkan `task_id` di memori tanpa batas maksimum entri.
4. Endpoint polling `/api/progress/{task_id}` tidak memiliki validasi sanitasi karakter pada `task_id` serta tidak memiliki rate limit khusus, sehingga dapat di-spam dengan polling frekuensi tinggi.

#### Dampak Risiko di Produksi
- CPU server mencapai penggunaan 100%, menyebabkan kegagalan respon (*timeout*) pada pengguna lain.
- I/O disk mengalami *bottleneck*, menyebabkan server lambat merespon antarmuka web.

#### Remediasi yang Diterapkan
1. **Pembatasan Konkurensi dengan `asyncio.Semaphore` (`app/main.py`)**:
   - `info_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFO)` (Default: 8).
   - `download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)` (Default: 3).
   - Akuisisi semafor dilindungi batas waktu tunggu 2 detik: `await asyncio.wait_for(semaphore.acquire(), timeout=2.0)`. Jika antrean penuh dan waktu habis, server segera merespon dengan status **HTTP 503 (Service Unavailable)** beserta pesan ramah yang meminta pengguna mencoba beberapa saat lagi.
2. **Pembatasan Kapasitas `ProgressTracker` (`app/downloader.py`)**:
   - Ditambahkan `max_entries: int = 2000`. Jika kapasitas tercapai saat ada task ID baru, entri tertua langsung di-eviksi.
3. **Validasi Format `task_id` & Rate Limiting Progress**:
   - Regex ketat `^[a-zA-Z0-9_-]{1,64}$` diterapkan pada `validate_task_id()`.
   - Endpoint `/api/progress/{task_id}` langsung menolak karakter berbahaya dengan status **HTTP 400**.
   - Ditambahkan pembatas laju independen `progress_rate_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60)` khusus untuk endpoint progress guna mencegah polling abuse.

---

### 2.4 [HIGH] Container Docker Berjalan sebagai `root` & Direktori `chmod 777`

#### Deskripsi Celah & Vektor Serangan Awal
1. `Dockerfile` bawaan tidak mendefinisikan direktif `USER`, sehingga seluruh proses (FastAPI, Uvicorn, Python, FFmpeg) berjalan dengan hak istimewa pengguna `root` di dalam container.
2. Direktori sementara `/tmp/dondu_downloads` atau `temp_downloads` dibuat dengan izin penuh `chmod 777`.

#### Dampak Risiko di Produksi
- **Container Escape & Privilege Escalation**: Jika ditemukan kerentanan *Remote Code Execution* (RCE) pada parser media `FFmpeg` (misalnya celah *buffer overflow* pada library demuxer C/C++) atau library `yt-dlp`, penyerang langsung mengeksekusi kode sebagai `root`. Hal ini membuka peluang pelarian dari container (*container breakout*) ke host OS apabila terdapat konfigurasi kernel/volume yang longgar.

#### Remediasi yang Diterapkan
1. **Dedicated Non-Root User & Group (`Dockerfile`)**:
   - Dibuat user dan grup khusus non-root bernama `dondu` dengan UID dan GID statis `10001`:
     ```dockerfile
     RUN groupadd -g 10001 dondu && \
         useradd -u 10001 -g dondu -s /bin/bash -m dondu
     ```
2. **Izin Direktori Minimum (Principle of Least Privilege)**:
   - Direktori kerja `/app` dan direktori unduhan `/tmp/dondu_downloads` diubah kepemilikannya ke `dondu:dondu`.
   - Izin direktori unduhan diatur ketat ke `chmod 700 /tmp/dondu_downloads`, sehingga hanya dapat dibaca dan ditulis oleh user `dondu`.
3. **Eksekusi Kontainer Aman**:
   - Mengaktifkan direktif `USER dondu` sebelum instruksi `CMD`.
   - Menambahkan opsi `--no-access-log` dan `--timeout-keep-alive 30` pada uvicorn di `CMD` untuk mengurangi beban penulisan log berlebih di container.

---

### 2.5 [MEDIUM] Sanitasi Skema URL Thumbnail, Header Keamanan HTTP, & Eksposur Swagger Docs

#### Deskripsi Celah & Vektor Serangan Awal
1. URL gambar thumbnail dari platform pihak ketiga langsung dimasukkan ke properti `src` elemen `<img>` pada antarmuka frontend tanpa pembersihan skema.
2. Server FastAPI tidak menyertakan header keamanan HTTP standar, sehingga rentan terhadap serangan *Clickjacking*, *MIME Sniffing*, dan penyisipan skrip berbahaya.
3. Rute dokumentasi Swagger (`/docs`) dan OpenAPI schema (`/openapi.json`) terbuka bebas secara publik di produksi.
4. Endpoint pemeriksaan status (`/health`) menampilkan nomor versi exact `yt-dlp` (`{"status": "ok", "yt_dlp_version": "202x.xx.xx"}`), yang memfasilitasi penyerang memetakan celah keamanan dari versi spesifik yang digunakan (*vulnerability fingerprinting*).

#### Dampak Risiko di Produksi
- Potensi serangan XSS dan pembajakan klik (*Clickjacking*) antarmuka aplikasi di dalam iframe situs jahat.
- Penyerang luar dapat membaca rute internal dan payload schema dengan mudah.

#### Remediasi yang Diterapkan
1. **Sanitasi URL Thumbnail (Backend & Frontend)**:
   - Backend (`app/downloader.py`): Fungsi `sanitize_thumbnail_url()` memastikan thumbnail hanya menggunakan protokol `http://` atau `https://`, panjang <= 2048 karakter, serta bebas dari spasi dan karakter kontrol ASCII.
   - Frontend (`static/app.js`): Fungsi `isSafeHttpUrl()` memvalidasi format string sebelum memasukkannya ke `previewThumbnail.src`.
2. **Middleware Header Keamanan Komprehensif (`app/main.py`)**:
   - Setiap respons HTTP kini otomatis dilengkapi dengan header:
     - `Content-Security-Policy`: `default-src 'self'; img-src 'self' https: http: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
     - `X-Content-Type-Options`: `nosniff`
     - `X-Frame-Options`: `DENY`
     - `Referrer-Policy`: `no-referrer`
     - `Permissions-Policy`: `camera=(), microphone=(), geolocation=()`
3. **Proteksi Dokumentasi API**:
   - Variabel `ENABLE_DOCS` ditambahkan ke `app/config.py` (Default: `false`).
   - Rute `/docs` dan `/openapi.json` mengembalikan status **HTTP 404** secara default. Administrator dapat mengaktifkannya hanya di lingkungan *development* atau staging.
4. **Hardening Endpoint `/health`**:
   - Field `yt_dlp_version` dihapus dari respons JSON. Endpoint `/health` kini hanya mengembalikan `{"status": "ok"}` tanpa membocorkan rincian komponen internal.

---

## 3. Analisis Desain: Default Durasi & Ukuran File Tanpa Batas (`0 = Unlimited`)

Pada versi sebelumnya, Dondu menerapkan batas durasi 60 menit dan batas ukuran file 500 MB. Dalam audit ini, konfigurasi default diubah menjadi:
- `MAX_DURATION_MINUTES=0` (0 = Tanpa batas durasi)
- `MAX_FILE_SIZE_MB=0` (0 = Tanpa batas ukuran file)

### Mengapa Desain Ini Aman Diterapkan di Dondu?
Membuka batasan durasi dan ukuran file sering kali menimbulkan kekhawatiran terhadap penipisan sumber daya (*resource exhaustion*). Namun, pada arsitektur Dondu yang baru, keamanan dan stabilitas sistem tidak lagi bertumpu pada pemotongan durasi file, melainkan dijamin melalui **lapisan pertahanan berlapis (defense-in-depth)**:

1. **Pembatasan Konkurensi Keras (*Hard Concurrency Limit*)**:
   - Dengan `MAX_CONCURRENT_DOWNLOADS=3`, server secara absolut tidak akan pernah memproses lebih dari 3 pekerjaan pengunduhan/transcoding secara simultan, terlepas dari seberapa besar file yang diunduh.
   - Permintaan ke-4 dan seterusnya akan menunggu di antrean semafor maksimal 2 detik sebelum ditolak secara anggun dengan HTTP 503.
2. **Pemisahan Thread Non-Blocking**:
   - Operasi `yt-dlp` dan `FFmpeg` dijalankan di dalam worker thread (`asyncio.to_thread`) yang terpisah dari *event loop* utama FastAPI. Antarmuka web dan pengecekan kesehatan server tetap responsif 100% meskipun proses download berukuran gigabyte sedang berlangsung.
3. **Pembersihan File Sementara Otomatis**:
   - Setiap file diunduh ke dalam folder UUID unik di dalam direktori sementara. Begitu pengunduhan selesai dan dikirim via streaming response ke klien, file langsung dihapus oleh `FileCleanupBackgroundTask`.
   - Pembersih berkala (*periodic cleanup task*) berjalan setiap 120 detik untuk membersihkan sisa file yang terputus di tengah jalan (*stale downloads*).
4. **Isolasi Memori Sementara (Opsional & Direkomendasikan)**:
   - Dengan menjalankan direktori unduhan di atas `tmpfs` (RAM terisolasi) berukuran tertentu (misal 2 GB), kapasitas disk fisik host tidak akan pernah terpengaruh.

> [!NOTE]
> Jika administrator menjalankan Dondu pada VPS dengan spesifikasi CPU/RAM yang sangat terbatas (misal RAM 512 MB atau 1 core), batas durasi dan ukuran file tetap dapat diaktifkan kapan saja dengan mengisi angka `> 0` pada environment variable `MAX_DURATION_MINUTES` dan `MAX_FILE_SIZE_MB`.

---

## 4. Rekomendasi Arsitektur & Kesiapan Produksi

Untuk memastikan Dondu beroperasi dengan performa tinggi dan keamanan maksimal di lingkungan publik, terapkan rekomendasi berikut:

### 4.1 Reverse Proxy & Terminasi TLS/HTTPS
**Status: WAJIB UNTUK PRODUKSI**

1. **Kebutuhan Akses Clipboard di Perangkat Mobile**:
   - Antarmuka Dondu menyediakan tombol "Tempel" yang memanfaatkan API browser `navigator.clipboard.readText()`.
   - Sesuai spesifikasi W3C dan kebijakan keamanan browser modern (iOS Safari, Android Chrome, desktop Chrome), **Clipboard API hanya dapat diakses dalam Secure Context (HTTPS)**.
   - Jika Dondu diakses melalui HTTP biasa (misal `http://ip-server:8000`), fitur tempel otomatis akan dinonaktifkan oleh browser demi keamanan privasi pengguna.
2. **Konfigurasi Reverse Proxy**:
   - Jalankan Dondu di balik Caddy atau Nginx.
   - Aktifkan `TRUST_PROXY_HEADERS=true` pada Dondu hanya jika reverse proxy telah dikonfigurasi untuk menimpa (*overwrite*) header `X-Forwarded-For`.

#### Contoh Konfigurasi Caddy (`Caddyfile`):
```caddy
dondu.domainanda.com {
    encode zstd gzip

    # Batasi ukuran request body jika diperlukan
    request_body {
        max_size 10MB
    }

    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

#### Contoh Konfigurasi Nginx (`/etc/nginx/sites-available/dondu`):
```nginx
server {
    listen 80;
    server_name dondu.domainanda.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name dondu.domainanda.com;

    ssl_certificate /etc/letsencrypt/live/dondu.domainanda.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dondu.domainanda.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Nonaktifkan buffering untuk streaming respons file besar
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

---

### 4.2 Manajemen Disk Sementara dengan `tmpfs` pada Docker
**Status: SANGAT DIREKOMENDASIKAN**

Gunakan mount `tmpfs` pada direktori file sementara saat menjalankan container Docker:
```bash
docker run -d \
  --name dondu-app \
  -p 8000:8000 \
  --tmpfs /tmp/dondu_downloads:rw,noexec,nosuid,size=2g \
  -e MAX_CONCURRENT_DOWNLOADS=3 \
  -e MAX_CONCURRENT_INFO=8 \
  dondu
```

**Keuntungan**:
- **Kecepatan I/O Maksimal**: Operasi penulisan video dan konversi MP3 berlangsung langsung di RAM, menghemat umur pakai SSD/NVMe server.
- **Perlindungan Disk Penuh**: Jika terjadi kegagalan penghapusan file, kapasitas memori dibatasi maksimal 2 GB dan tidak akan mengganggu stabilitas partisi root host server.
- **Keamanan Tambahan**: Opsi `noexec,nosuid` memastikan tidak ada file yang dapat dieksekusi sebagai binari dari dalam direktori unduhan sementara.

---

### 4.3 Skalabilitas Arsitektur Multi-Worker / Multi-Instance

Arsitektur saat ini menggunakan komponen *in-memory* (`asyncio.Semaphore`, `SlidingWindowRateLimiter`, `ProgressTracker`) yang dioptimalkan untuk single-node/single-process. Apabila trafik berkembang menjadi ribuan permintaan simultan:
1. **Penyimpanan State Terpusat (Redis)**:
   - Gantikan in-memory `SlidingWindowRateLimiter` dengan Redis token bucket / sliding window via Redis EVAL script.
   - Pindahkan `ProgressTracker` ke Redis Pub/Sub atau Redis Key-Value dengan TTL otomatis.
2. **Antrean Pekerjaan Asinkron (Task Queue)**:
   - Pisahkan API gateway (FastAPI) dengan worker pemroses media menggunakan Celery, ARQ, atau BullMQ.
   - File hasil unduhan disimpan sementara ke object storage privat (seperti AWS S3 atau MinIO) dengan *pre-signed download URL* yang memiliki masa kedaluwarsa 10 menit.

---

### 4.4 Strategi Menghadapi Pemblokiran IP Data Center oleh Platform Video

Platform seperti YouTube, Instagram, dan TikTok secara aktif memantau dan memblokir alamat IP yang berasal dari penyedia cloud besar (AWS, DigitalOcean, Hetzner, GCP, OVH) melalui deteksi CAPTCHA (*Sign in to confirm you're not a bot*).

**Langkah Mitigasi di Lingkungan Produksi**:
1. **Otomasi Pembaruan `yt-dlp`**:
   - `yt-dlp` merilis perbaikan hampir setiap minggu untuk mengatasi perubahan algoritma platform. Pasang cronjob di server untuk memperbarui image Docker atau library secara berkala:
     ```bash
     0 3 * * * docker exec dondu-app pip install -U yt-dlp && docker restart dondu-app
     ```
2. **Penggunaan File Cookies (`COOKIES_FILE`)**:
   - Untuk platform Instagram dan Facebook yang sering mewajibkan sesi login, sediakan file cookies berformat Netscape (`cookies.txt`).
   - > [!IMPORTANT]
     > **Gunakan akun *burner* (akun sekunder khusus bot)**, BUKAN akun pribadi penting Anda, untuk mencegah risiko pemblokiran akun oleh platform media sosial.
3. **Konfigurasi Proxy Egress (Residential / Rotasi Proxy)**:
   - Jika server terkena IP blacklist platform, arahkan trafik keluar `yt-dlp` melalui proxy perumahan (*residential proxy*) dengan menyetel parameter proxy yt-dlp.

---

## 5. Checklist Sebelum Go-Live (Pre-Deployment Checklist)

Gunakan tabel checklist berikut sebelum meluncurkan aplikasi Dondu ke domain publik:

| Kategori | Butir Pengecekan | Status Wajib | Verifikasi |
| :--- | :--- | :--- | :--- |
| **Keamanan Jaringan** | Domain diarahkan ke Reverse Proxy dengan sertifikat TLS/HTTPS aktif | WAJIB | Tes akses `https://domain.com` dan periksa ikon gembok browser. |
| **Clipboard API** | Fitur tombol "Tempel" berfungsi mulus di browser mobile (Safari/Chrome) | WAJIB | Buka web via HP, salin tautan, klik "Tempel". Pastikan dialog izin clipboard muncul. |
| **Proxy Trust** | Variabel `TRUST_PROXY_HEADERS=true` hanya disetel jika reverse proxy menimpa header `X-Forwarded-For` | WAJIB | Periksa log IP di backend dan pastikan IP klien bukan loopback atau hasil injeksi. |
| **API Docs Exposure** | Variabel `ENABLE_DOCS=false` di lingkungan produksi | WAJIB | Akses `https://domain.com/docs` dan pastikan menghasilkan halaman 404 Not Found. |
| **Health Check** | Endpoint `/health` merespon `200 OK` tanpa kebocoran informasi versi pustaka | WAJIB | Jalankan `curl https://domain.com/health` -> `{"status":"ok"}`. |
| **Container User** | Container Docker berjalan dengan user non-root `dondu` (UID `10001`) | WAJIB | Jalankan `docker exec dondu-app id` -> `uid=10001(dondu)`. |
| **Isolasi Temp Dir** | Direktori unduhan sementara dimount menggunakan `--tmpfs` atau bervolume terisolasi | DIREKOMENDASIKAN | Periksa `df -h` di dalam container. |
| **Batas Konkurensi** | `MAX_CONCURRENT_DOWNLOADS` (3) dan `MAX_CONCURRENT_INFO` (8) disesuaikan dengan kapasitas CPU server | WAJIB | Lakukan uji beban ringan; server merespon 503 jika antrean penuh tanpa crash. |
| **Unit Test Suite** | Seluruh 41 unit & integration test lolos pengujian otomatis | WAJIB | Jalankan `python -m unittest discover -s tests -v`. |

---

## 6. Kesimpulan

Melalui serangkaian perbaikan pada Task 1 hingga Task 4, aplikasi **Dondu** telah bertransformasi dari prototipe fungsional menjadi sistem pengunduh media yang tangguh, aman, dan berstandar produksi. Seluruh celah kritis mulai dari SSRF, manipulasi rate limit, DoS proses, hingga isolasi hak akses container telah ditutup secara permanen.

Dengan menerapkan rekomendasi arsitektur di atas (khususnya penggunaan HTTPS untuk kompatibilitas Clipboard API mobile dan isolasi folder unduhan sementara), Dondu siap beroperasi melayani pengguna dengan cepat, andal, dan aman.
