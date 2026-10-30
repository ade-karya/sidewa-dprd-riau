# SIDEWA — image produksi
# Build dari direktori dprd-riau:  docker build -f deploy/Dockerfile -t sidewa:1.2.0 .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SIDEWA_ENV=production

# Dependensi sistem untuk dlib, Pillow, dan PostgreSQL client.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libopenblas-dev \
        liblapack-dev \
        libx11-dev \
        libgtk-3-dev \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libpq5 \
        curl \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Lapisan dependensi dipisah agar cache build efisien.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && apt-get purge -y build-essential cmake libx11-dev libgtk-3-dev \
    && apt-get autoremove -y

COPY app ./app
# Foto contoh staf untuk `python -m app.cli seed-staff` (idempoten).
COPY seed_assets ./seed_assets
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && addgroup --system sidewa \
    && adduser --system --ingroup sidewa --home /app sidewa \
    && mkdir -p /app/data/media \
    && chown -R sidewa:sidewa /app

USER sidewa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers"]
