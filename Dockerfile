FROM python:3.12.11-bookworm AS api-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /api
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY workspace_api/ ./workspace_api
RUN python -m pip wheel --no-cache-dir --wheel-dir /api/wheels .[prod]

FROM node:22-alpine3.19 AS ui-builder
RUN apk add --no-cache \
    bash=5.2.21-r0 \
    rsync=3.4.0-r1
WORKDIR /ui
COPY workspace_ui/build_dist.sh .
COPY workspace_ui/luigi-shell ./luigi-shell
COPY workspace_ui/management ./management
RUN ./build_dist.sh

FROM python:3.12.11-bookworm

ARG VERSION=latest
LABEL version=${VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    prometheus_multiproc_dir=/var/tmp/prometheus_multiproc_dir \
    UI_DIST_DIR=/home/app/static

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates mailcap \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p "$prometheus_multiproc_dir" "$UI_DIST_DIR"

RUN groupadd -g 1000 app && useradd -mr -d /home/app -s /bin/bash -u 1000 -g 1000 app

COPY --from=api-builder /api/wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --from=ui-builder --chown=app:app /ui/dist/ ${UI_DIST_DIR}/

COPY resources/gunicorn.conf.py /etc/gunicorn.conf.py

RUN chown -R app:app "$prometheus_multiproc_dir"
USER app
WORKDIR /home/app

EXPOSE 8080
CMD ["gunicorn", "--config", "/etc/gunicorn.conf.py"]
