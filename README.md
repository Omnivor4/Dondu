# Dondu

**Unduh video & MP3 dengan cepat.**

**Dondu** adalah aplikasi web pengunduh video (MP4) dan audio (MP3) berbasis **Python 3.11+**, **FastAPI**, **yt-dlp**, dan **FFmpeg**, dengan antarmuka **HTML + CSS + JavaScript Vanilla** yang ringan, responsif (mobile-first), dan mendukung mode terang/gelap otomatis.

---

## Fitur Utama

- **Platform yang Didukung**: TikTok, Instagram (Reels/post publik), Facebook (video publik), X/Twitter, dan YouTube (termasuk Shorts). URL di luar domain resmi platform tersebut ditolak otomatis di sisi backend.
- **Pratinjau Cerdas (`Cek Video`)**: Menampilkan judul, thumbnail, durasi, nama kreator/uploader, platform, serta daftar resolusi video yang benar-benar tersedia pada tautan tersebut tanpa mengunduh terlebih dahulu.
- **Pilihan Format Fleksibel**:
  - **Video (MP4)**: Opsi **Terbaik otomatis** serta kualitas dinamis (`360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`) dengan penggabungan video+audio ke codec kompatibel universal (H.264/AAC + `faststart`).
  - **Audio (MP3)**: Pilihan bitrate `128`, `192`, `256`, atau `320 kbps` yang dikonversi melalui FFmpeg lengkap dengan metadata ID3 dan gambar sampul (*cover art*) bila tersedia.
- **Keamanan Berlapis & Produksi Siap Pakai**:
  - **Proteksi SSRF & Open Redirect**: Memblokir IP internal/privat, loopback, link-local metadata cloud, kredensial tersemat, port non-standar, serta memvalidasi ulang URL target pasca-ekstraksi shortlink.
  - **Batas Konkurensi Keras (`asyncio.Semaphore`)**: Melindungi server dari kehabisan CPU/RAM akibat proses FFmpeg simultan; secara default durasi dan ukuran file diatur **tanpa batas (`0 = unlimited`)**.
  - **Pembatas Laju (*Rate Limiting*) Terisolasi**: Mencegah serangan flooding dan pembobolan header proxy (`X-Forwarded-For`), dilengkapi pembatasan memori otomatis (FIFO eviction).
  - **Container Docker Non-Root**: Berjalan di bawah pengguna khusus `dondu` (UID `10001`) dengan izin folder ketat (`chmod 700`).
  - **Header Keamanan HTTP**: CSP ketat, X-Frame-Options (DENY), X-Content-Type-Options (nosniff), dan Swagger UI dinonaktifkan secara default di produksi.
  - **Bersih & Tanpa Riwayat**: Setiap unduhan diproses di folder sementara unik dan langsung dihapus setelah streaming selesai, ditambah pembersihan berkala otomatis setiap 2 menit untuk file kedaluwarsa.

---

## Struktur Proyek

```text
dondu/
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ config.py
â”‚   â”œâ”€â”€ downloader.py
â”‚   â”œâ”€â”€ main.py
â”‚   â”œâ”€â”€ rate_limiter.py
â”‚   â”œâ”€â”€ schemas.py
â”‚   â””â”€â”€ validators.py
â”œâ”€â”€ static/
â”‚   â”œâ”€â”€ index.html
â”‚   â”œâ”€â”€ styles.css
â”‚   â””â”€â”€ app.js
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ test_api_hardening.py
â”‚   â”œâ”€â”€ test_security_backend.py
â”‚   â””â”€â”€ test_validators.py
â”œâ”€â”€ .dockerignore
â”œâ”€â”€ .env.example
â”œâ”€â”€ AUDIT_REPORT.md
â”œâ”€â”€ Dockerfile
â”œâ”€â”€ requirements.txt
â””â”€â”€ README.md
```

---

## 1. Instalasi FFmpeg (Wajib untuk Instalasi Lokal)

Dondu membutuhkan **FFmpeg** untuk menggabungkan aliran video + audio resolusi tinggi (MP4) dan mengonversi audio ke MP3 beserta metadata/thumbnail.

### Windows
Pilih salah satu cara berikut di PowerShell / Terminal:
```powershell
# Menggunakan Winget (direkomendasikan)
winget install Gyan.FFmpeg

# Atau menggunakan Chocolatey
choco install ffmpeg

# Atau menggunakan Scoop
scoop install ffmpeg
```
Setelah instalasi selesai, tutup dan buka kembali terminal, lalu pastikan perintah `ffmpeg -version` berjalan.

### Linux (Ubuntu / Debian)
```bash
sudo apt update && sudo apt install -y ffmpeg
```

### Linux (Fedora / RHEL / Arch)
```bash
# Fedora
sudo dnf install -y ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

### macOS (Homebrew)
```bash
brew install ffmpeg
```

---

## 2. Cara Menjalankan Secara Lokal

1. Masuk ke direktori proyek `dondu/`:
   ```bash
   cd dondu
   ```

2. Buat dan aktifkan *virtual environment* Python 3.11+:
   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Instal seluruh dependensi:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. (Opsional) Salin file konfigurasi `.env.example` menjadi `.env`:
   ```bash
   cp .env.example .env
   ```

5. Jalankan server FastAPI dengan Uvicorn:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

6. Buka browser di:
   - Aplikasi Web: `http://localhost:8000`
   - Endpoint Health Check: `http://localhost:8000/health`

---

## 3. Cara Menjalankan dengan Docker

Dockerfile sudah dikonfigurasi menggunakan **Python 3.11**, **FFmpeg**, dan berjalan aman sebagai user non-root `dondu` (UID `10001`).

1. Bangun (*build*) image Docker bernama `dondu`:
   ```bash
   docker build -t dondu .
   ```

2. Jalankan container `dondu` (dengan flag keamanan produksi yang direkomendasikan):
   ```bash
   docker run -d \
     --name dondu-app \
     -p 8000:8000 \
     --tmpfs /tmp/dondu_downloads:rw,noexec,nosuid,size=2g \
     -e MAX_DURATION_MINUTES=0 \
     -e MAX_FILE_SIZE_MB=0 \
     -e MAX_CONCURRENT_DOWNLOADS=3 \
     -e MAX_CONCURRENT_INFO=8 \
     -e RATE_LIMIT_PER_MINUTE=10 \
     dondu
   ```

   > **Catatan Flag Keamanan Produksi:**
   > - `--tmpfs /tmp/dondu_downloads:rw,noexec,nosuid,size=2g`: Memetakan folder unduhan sementara ke memori RAM terisolasi. Hal ini mempercepat proses penulisan file, mencegah keausan disk host, mengeliminasi risiko disk penuh (*disk exhaustion*), serta mencegah eksekusi file biner (`noexec`).

3. Akses aplikasi di `http://localhost:8000`.

---

## 4. Daftar Environment Variable

Konfigurasi aplikasi dapat disesuaikan melalui file `.env` atau *environment variables* container:

| Variabel | Default | Deskripsi |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Alamat host tempat server mendengarkan koneksi. |
| `PORT` | `8000` | Port HTTP server. |
| `LOG_LEVEL` | `INFO` | Tingkat log aplikasi (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `TRUST_PROXY_HEADERS` | `false` | Percayai header proxy `X-Forwarded-For` dan `X-Real-IP`. Setel `true` hanya jika server berada di balik reverse proxy terpercaya (Nginx/Caddy/Cloudflare). |
| `ENABLE_DOCS` | `false` | Mengaktifkan antarmuka Swagger UI (`/docs`) dan skema OpenAPI (`/openapi.json`). Nonaktif secara default di produksi. |
| `MAX_CONCURRENT_INFO` | `8` | Batas maksimum konkurensi untuk proses ekstraksi info media secara simultan (`asyncio.Semaphore`). |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Batas maksimum konkurensi untuk proses unduh & konversi media secara simultan (`asyncio.Semaphore`). |
| `RESOLVE_DNS_SSRF_CHECK` | `false` | Melakukan resolusi DNS aktif sebelum request untuk memastikan IP tujuan bukan alamat privat/internal. |
| `MAX_DURATION_MINUTES` | `0` | Batas maksimum durasi video dalam menit (`0` = tanpa batas / *unlimited*; isi angka `> 0` jika ingin membatasi). |
| `MAX_FILE_SIZE_MB` | `0` | Batas maksimum ukuran file hasil unduhan dalam MB (`0` = tanpa batas / *unlimited*; isi angka `> 0` jika ingin membatasi). |
| `RATE_LIMIT_PER_MINUTE` | `10` | Jumlah maksimum permintaan per menit per alamat IP pada endpoint info dan unduh. |
| `TEMP_DIR` | `temp_downloads` | Lokasi direktori sementara untuk memproses file unduhan (pada Docker otomatis dialihkan ke `/tmp/dondu_downloads`). |
| `CLEANUP_MAX_AGE_MINUTES` | `15` | Batas umur maksimum file sementara sebelum dihapus otomatis oleh pembersih berkala. |
| `CLEANUP_INTERVAL_SECONDS` | `120` | Interval waktu antar pengecekan pembersihan berkala (dalam detik). |
| `COOKIES_FILE` | *(kosong)* | Path opsional ke file cookies berformat Netscape (`cookies.txt`) bila diperlukan untuk konten tertentu. |

---

## 5. Pengujian Keamanan & Unit Test

Dondu dilengkapi dengan suite pengujian otomatis komprehensif yang mencakup 41 pengujian unit dan integrasi untuk memverifikasi fungsionalitas, keamanan, dan ketahanan sistem.

Untuk menjalankan seluruh rangkaian pengujian:
```bash
python -m unittest discover -s tests -v
```

### Cakupan Pengujian:
1. **`tests/test_validators.py` (13 pengujian)**:
   - Validasi domain platform resmi (YouTube, TikTok, Instagram, Facebook, X).
   - Penolakan domain tak didukung dan domain *spoofing* (`fake-youtube.com`, `notx.com`).
   - Penolakan URL dengan kredensial tersemat (`user:pass@domain`).
   - Pembatasan port ketat hanya port standar (`80`, `443`).
   - Proteksi SSRF terhadap localhost, hostname internal (`.internal`, `.local`), IP privat, link-local, cloud metadata (`169.254.169.254`), multicast, dan format IPv4-mapped IPv6 (`::ffff:127.0.0.1`).
   - Validasi format `task_id` dan skema Pydantic.
   - Sanitasi nama file dan pembuatan header RFC 5987 `Content-Disposition`.
2. **`tests/test_security_backend.py` (15 pengujian)**:
   - Pencegahan bypass rate limiter melalui pemalsuan header `X-Forwarded-For`.
   - Pembatasan kapasitas memori dan eviksi FIFO pada `SlidingWindowRateLimiter` (`max_tracked_ips=10000`).
   - Pembatasan kapasitas memori dan eviksi FIFO pada `ProgressTracker` (`max_entries=2000`).
   - Sanitasi URL thumbnail mencegah injeksi skema `javascript:`, `data:`, `file:`.
   - Verifikasi pembatasan protokol `yt-dlp` (`allowed_protocols: ["http", "https"]`).
   - Proteksi SSRF & open redirect pasca-ekstraksi: verifikasi bahwa unduhan dibatalkan sebelum `ydl.download()` jika redirect mengarah ke domain/IP terlarang.
3. **`tests/test_api_hardening.py` (13 pengujian)**:
   - Verifikasi header keamanan HTTP (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).
   - Verifikasi endpoint `/health` tidak membocorkan versi pustaka `yt_dlp_version`.
   - Verifikasi endpoint dokumentasi `/docs` dan `/openapi.json` mengembalikan 404 saat `ENABLE_DOCS=false`.
   - Penolakan karakter berbahaya pada endpoint progress `/api/progress/{task_id}`.
   - Pengujian batas waktu semafor konkurensi (`info_semaphore` dan `download_semaphore`) yang merespon HTTP 503 saat server sibuk.
   - Pembatasan laju independen pada polling progress (`progress_rate_limiter`).
   - Verifikasi konfigurasi default *unlimited* (`0`) tetap mengizinkan video berdurasi panjang.

---

## 6. Laporan Audit Keamanan

Untuk membaca analisis mendalam mengenai seluruh kerentanan yang telah diperbaiki, arsitektur keamanan, rekomendasi reverse proxy & TLS (diperlukan agar Clipboard API berfungsi di ponsel), dan checklist pra-produksi, silakan baca dokumentasi lengkap di:
ðŸ‘‰ **[AUDIT_REPORT.md](AUDIT_REPORT.md)**

---

## 7. Cara Memperbarui `yt-dlp`

Platform video seperti YouTube, TikTok, Instagram, Facebook, dan X sering memperbarui sistem pemutar atau API mereka. Jika proses cek atau unduh tiba-tiba gagal di semua tautan, perbarui `yt-dlp` ke versi paling mutakhir:

### Pada Instalasi Lokal
```bash
pip install -U yt-dlp
```

### Pada Docker
```bash
# Memperbarui langsung di dalam container yang sedang berjalan (sebagai root karena container berjalan dengan user non-root dondu)
docker exec -u 0 -it dondu-app pip install -U yt-dlp && docker restart dondu-app

# Atau bangun ulang image tanpa cache (direkomendasikan)
docker build --no-cache -t dondu .
```

---

## 8. Catatan Batasan & Ketentuan Penggunaan

- **Kebutuhan Cookies pada Instagram & Facebook**: Meskipun Dondu mendukung tautan Reels dan video publik, **Instagram** dan **Facebook** terkadang membatasi akses tanpa sesi (*guest access*) untuk video tertentu atau dari alamat IP server tertentu. Jika hal ini terjadi, Anda dapat menyediakan file cookies berformat Netscape melalui variabel environment `COOKIES_FILE` (gunakan akun sekunder/*burner*, bukan akun utama).
- **Kebutuhan HTTPS untuk Clipboard API**: Di browser smartphone (Safari iOS / Chrome Android), fitur tombol "Tempel" mewajibkan konteks aman HTTPS agar dapat membaca isi papan klip secara otomatis.
- **Perubahan Platform**: Layanan dapat sewaktu-waktu mengalami gangguan ekstraksi ketika platform tujuan mengubah struktur halaman/API mereka sampai pembaruan `yt-dlp` berikutnya dirilis (`pip install -U yt-dlp`).
- **Hak Cipta & Privasi**: Gunakan Dondu hanya untuk mengunduh konten milik sendiri, berlisensi terbuka (*Creative Commons* / domain publik), atau yang telah diizinkan oleh pembuatnya. Konten ber-DRM, siaran langsung aktif, dan akun privat tidak didukung.
