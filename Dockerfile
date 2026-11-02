FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN useradd --create-home --uid 10001 videoluk \
    && mkdir -p /data \
    && chown -R videoluk:videoluk /app /data

ENV VIDEOLUK_HOST=0.0.0.0 \
    VIDEOLUK_PORT=8787 \
    VIDEOLUK_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 8787
USER videoluk
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3)"
CMD ["python", "server.py"]
