FROM python:3.11-slim

LABEL maintainer="Forte"
LABEL description="Forte - Aplikasi Web Downloader Video & MP3"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    TEMP_DIR=/tmp/forte_downloads

WORKDIR /app

# Instal FFmpeg dan sertifikat SSL
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Instal dependensi Python dan pastikan yt-dlp selalu versi terbaru saat build
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -U yt-dlp

# Salin seluruh kode aplikasi
COPY app/ ./app/
COPY static/ ./static/

# Buat direktori sementara dengan izin penuh
RUN mkdir -p /tmp/forte_downloads && chmod 777 /tmp/forte_downloads

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

