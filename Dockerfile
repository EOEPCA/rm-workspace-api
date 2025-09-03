# Python builder (3.12.6)
FROM python:3.12.6-slim-bookworm AS py-builder

WORKDIR /usr/src/app/workspace_api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

COPY workspace_api/pyproject.toml workspace_api/README.md ./
COPY workspace_api/ ./
RUN pip wheel --no-cache-dir --wheel-dir /usr/src/app/wheels .[prod]

# UI builder
FROM node:20-alpine AS ui-builder
WORKDIR /ui
COPY workspace_ui/package*.json ./
RUN npm ci
COPY workspace_ui/ ./
RUN npm run build

# Final image (3.12.6)
FROM python:3.12.6-slim-bookworm

ARG VERSION=latest
LABEL version=${VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    prometheus_multiproc_dir=/var/tmp/prometheus_multiproc_dir

RUN apt-get update \
 && apt-get install -y --no-install-recommends mailcap \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p "$prometheus_multiproc_dir"

RUN groupadd -g 1000 app \
 && useradd -mr -d /home/app -s /bin/bash -u 1000 -g 1000 app

COPY --from=py-builder /usr/src/app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

COPY resources/gunicorn.conf.py /etc/gunicorn.conf.py

USER app
WORKDIR /home/app
COPY --from=ui-builder /ui/dist ./static

USER root
RUN chown -R app:app "$prometheus_multiproc_dir"
USER app

EXPOSE 8080
CMD ["gunicorn", "--config", "/etc/gunicorn.conf.py", "--workers=3", "-k", "uvicorn.workers.UvicornWorker", "--log-level=INFO", "workspace_api:app"]
