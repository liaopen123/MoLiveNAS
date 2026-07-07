FROM python:3.13-slim-trixie

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg imagemagick libimage-exiftool-perl libheif-examples intel-media-va-driver ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN useradd --system --uid 10001 --create-home molive \
    && mkdir -p /input /output /data \
    && chown -R molive:molive /app /output /data

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER molive
EXPOSE 8787
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "molive_nas", "daemon"]
