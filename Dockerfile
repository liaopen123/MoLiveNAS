ARG HDR_BRIDGE_IMAGE=molive-hdr-bridge-experiment
FROM ${HDR_BRIDGE_IMAGE} AS hdr_bridge

FROM python:3.13-slim-trixie

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg imagemagick libimage-exiftool-perl libheif-examples intel-media-va-driver ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=hdr_bridge /code/aa-photo-bridge /usr/local/bin/aa-photo-bridge
COPY --from=hdr_bridge /code/libheif /usr/local/lib/libheif
COPY . /app
RUN useradd --system --uid 10001 --create-home molive \
    && mkdir -p /input /output /data \
    && chown -R molive:molive /app /output /data

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    LIBHEIF_PLUGIN_PATH=/usr/local/lib/libheif \
    MOLIVE_ULTRAHDR_BRIDGE=/usr/local/bin/aa-photo-bridge
USER molive
EXPOSE 8787
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "molive_nas", "daemon"]
