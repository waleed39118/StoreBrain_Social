# syntax=docker/dockerfile:1
# Ada server image. Build with voice:  docker build --build-arg WITH_VOICE=1 .
FROM python:3.13-slim AS base
ARG WITH_VOICE=0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eux; \
    if [ "$WITH_VOICE" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng && rm -rf /var/lib/apt/lists/*; \
    fi; \
    useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin ada

WORKDIR /app
COPY requirements.txt requirements-voice.txt ./
RUN set -eux; \
    if [ "$WITH_VOICE" = "1" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install -r requirements-voice.txt; \
    else pip install -r requirements.txt; fi

COPY --chown=ada:ada alembic.ini ./
COPY --chown=ada:ada app ./app
COPY --chown=ada:ada migrations ./migrations
COPY --chown=ada:ada web ./web

RUN mkdir -p /data && chown ada:ada /data
USER ada
ENV ADA_DATABASE_URL=sqlite:////data/ada.db ADA_BACKUP_DIR=/data/backups ADA_TTS_OUTPUT_DIR=/data/tts \
    HF_HOME=/data/models XDG_CACHE_HOME=/data/cache
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
# Single worker: SQLite writer + in-process rate limits/long-polls. Scale up with PostgreSQL.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "*", "--no-server-header"]
