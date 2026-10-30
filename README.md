# Forte

**Unduh video & MP3 dengan cepat.**

**Forte** adalah aplikasi web pengunduh video (MP4) dan audio (MP3) berbasis **Python 3.11+**, **FastAPI**, **yt-dlp**, dan **FFmpeg**, dengan antarmuka **HTML + CSS + JavaScript Vanilla** yang ringan, responsif (mobile-first), dan mendukung mode terang/gelap otomatis.

---

## Fitur Utama

- **Platform yang Didukung**: TikTok, Instagram (Reels/post publik), Facebook (video publik), X/Twitter, dan YouTube (termasuk Shorts). URL di luar domain resmi platform tersebut ditolak otomatis di sisi backend.
- **Pratinjau Cerdas (`Cek Video`)**: Menampilkan judul, thumbnail, durasi, nama kreator/uploader, platform, serta daftar resolusi video yang benar-benar tersedia pada tautan tersebut tanpa mengunduh terlebih dahulu.
- **Pilihan Format Fleksibel**:
  - **Video (MP4)**: Opsi **Terbaik otomatis** serta kualitas dinamis (`360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`) dengan penggabungan video+audio ke codec kompatibel universal (H.264/AAC + `faststart`).
  - **Audio (MP3)**: Pilihan bitrate `128`, `192`, `256`, atau `320 kbps` yang dikonversi melalui FFmpeg lengkap dengan metadata ID3 dan gambar sampul (*cover art*) bila tersedia.
- **Aman, Bersih, & Tanpa Riwayat**:
  - Setiap unduhan diproses di folder sementara unik dan langsung dihapus setelah terkirim ke browser, ditambah pembersihan berkala otomatis setiap 2 menit untuk menghapus file yang berusia lebih dari 15 menit.
  - Dilengkapi pembatas laju (*rate limiting*) per IP, batas durasi video, batas ukuran file, eksekusi *non-blocking* di *worker thread*, dan tidak menyimpan riwayat tautan ataupun data pengguna.

---

## Struktur Proyek

```text
forte/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── downloader.py
│   ├── main.py
│   ├── rate_limiter.py
│   ├── schemas.py
│   └── validators.py
├── static/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── .dockerignore
├── .env.example
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 1. Instalasi FFmpeg (Wajib untuk Instalasi Lokal)

Forte membutuhkan **FFmpeg** untuk menggabungkan aliran video + audio resolusi tinggi (MP4) dan mengonversi audio ke MP3 beserta metadata/thumbnail.

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

1. Masuk ke direktori proyek `forte/`:
   ```bash
   cd forte
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

Dockerfile sudah dilengkapi dengan **Python 3.11** dan **FFmpeg** sehingga Anda tidak perlu menginstal FFmpeg secara manual di host.

1. Bangun (*build*) image Docker bernama `forte`:
   ```bash
   docker build -t forte .
   ```

2. Jalankan container `forte`:
   ```bash
   docker run -d \
     --name forte-app \
     -p 8000:8000 \
     -e MAX_DURATION_MINUTES=60 \
     -e MAX_FILE_SIZE_MB=500 \
     -e RATE_LIMIT_PER_MINUTE=10 \
     forte
   ```

3. Akses aplikasi di `http://localhost:8000`.

---

## 4. Daftar Environment Variable

| Variabel | Default | Deskripsi |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Alamat host tempat server mendengarkan koneksi. |
| `PORT` | `8000` | Port HTTP server. |
| `LOG_LEVEL` | `INFO` | Tingkat log aplikasi (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `MAX_DURATION_MINUTES` | `60` | Batas maksimum durasi video yang diizinkan (dalam menit). |
| `MAX_FILE_SIZE_MB` | `500` | Batas maksimum ukuran file hasil unduhan (dalam MB). |
| `RATE_LIMIT_PER_MINUTE` | `10` | Jumlah maksimum permintaan per menit per alamat IP. |
| `TEMP_DIR` | `temp_downloads` | Lokasi direktori sementara untuk memproses file unduhan. |
| `CLEANUP_MAX_AGE_MINUTES` | `15` | Batas umur maksimum file sementara sebelum dihapus otomatis oleh pembersih berkala. |
| `CLEANUP_INTERVAL_SECONDS` | `120` | Interval waktu antar pengecekan pembersihan berkala (dalam detik). |
| `COOKIES_FILE` | *(kosong)* | Path opsional ke file cookies berformat Netscape (`cookies.txt`) bila diperlukan untuk konten tertentu. |

---

## 5. Cara Memperbarui `yt-dlp`

Platform video seperti YouTube, TikTok, Instagram, Facebook, dan X sering memperbarui sistem pemutar atau API mereka. Jika proses cek atau unduh tiba-tiba gagal di semua tautan, perbarui `yt-dlp` ke versi paling mutakhir:

### Pada Instalasi Lokal
```bash
pip install -U yt-dlp
```

### Pada Docker
```bash
# Memperbarui langsung di dalam container yang sedang berjalan
docker exec -it forte-app pip install -U yt-dlp && docker restart forte-app

# Atau bangun ulang image tanpa cache
docker build --no-cache -t forte .
```

---

## 6. Catatan Batasan & Ketentuan Penggunaan

- **Kebutuhan Cookies pada Instagram & Facebook**: Meskipun Forte mendukung tautan Reels dan video publik, **Instagram** dan **Facebook** terkadang membatasi akses tanpa sesi (*guest access*) untuk video tertentu atau dari alamat IP server tertentu. Jika hal ini terjadi, Anda dapat menyediakan file cookies berformat Netscape melalui variabel environment `COOKIES_FILE`.
- **Perubahan Platform**: Layanan dapat sewaktu-waktu mengalami gangguan ekstraksi ketika platform tujuan mengubah struktur halaman/API mereka sampai pembaruan `yt-dlp` berikutnya dirilis (`pip install -U yt-dlp`).
- **Hak Cipta & Privasi**: Gunakan Forte hanya untuk mengunduh konten milik sendiri, berlisensi terbuka (*Creative Commons* / domain publik), atau yang telah diizinkan oleh pembuatnya. Konten ber-DRM, siaran langsung aktif, dan akun privat tidak didukung.

