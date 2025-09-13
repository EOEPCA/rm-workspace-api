FROM python:3.12.6-slim-bookworm AS api-builder
WORKDIR /api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY workspace_api/ ./workspace_api
RUN pip wheel --no-cache-dir --wheel-dir /api/wheels .[prod]

FROM node:22-alpine AS ui-builder
RUN apk add --no-cache \
    bash=5.2.26-r0 \
    rsync=3.3.0-r0
WORKDIR /ui
#COPY workspace_ui/package.json workspace_ui/package-lock.json workspace_ui/quasar.config.ts workspace_ui/index.html ./
#RUN npm ci
COPY workspace_ui/build_dist.sh .
COPY workspace_ui/luigi-shell ./luigi-shell
COPY workspace_ui/management ./management
RUN ./build_dist.sh

FROM python:3.12.6-slim-bookworm

ARG VERSION=latest
LABEL version=${VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    prometheus_multiproc_dir=/var/tmp/prometheus_multiproc_dir \
    UI_DIST_DIR=/home/app/static

RUN apt-get update \
 && apt-get install -y --no-install-recommends mailcap \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p "$prometheus_multiproc_dir" "$UI_DIST_DIR"

RUN groupadd -g 1000 app && useradd -mr -d /home/app -s /bin/bash -u 1000 -g 1000 app

COPY --from=api-builder /api/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --from=ui-builder --chown=app:app /ui/dist/ ${UI_DIST_DIR}/

COPY resources/gunicorn.conf.py /etc/gunicorn.conf.py

RUN chown -R app:app "$prometheus_multiproc_dir"
USER app
WORKDIR /home/app

EXPOSE 8080
CMD ["gunicorn", "--config", "/etc/gunicorn.conf.py"]
