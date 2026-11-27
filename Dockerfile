ARG VERSION=0.0.0+local

FROM python:3.12.16-trixie@sha256:5411fa1b302c43f510324381162b5f5d0d93b9ee2af538f09d944f0d290ee3cb AS api-base

COPY --from=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /api
COPY pyproject.toml uv.lock README.md ./

FROM api-base AS api-deps
RUN uv sync --locked --no-dev --extra prod --no-install-project --no-cache

FROM api-deps AS api-builder
COPY workspace_api/ ./workspace_api
ARG VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WORKSPACE_API="$VERSION" \
    uv sync --locked --no-dev --extra prod --no-editable --no-cache

FROM api-base AS api-test-deps
RUN uv sync --locked --extra dev --extra prod --no-install-project --no-cache

FROM api-test-deps AS api-test
COPY . .
ARG VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WORKSPACE_API="$VERSION" \
    uv sync --locked --extra dev --extra prod --no-editable --no-cache \
 && KUBECONFIG=/tmp/no-cluster-config uv run --no-sync pytest workspace_api/tests

FROM node:22.23.5-alpine3.23@sha256:6868d4695b947ee120bffaa463fecd68cde370d7bfec92955e7c8ac576b4f475 AS ui-deps
WORKDIR /ui/management
COPY workspace_ui/management/package.json workspace_ui/management/package-lock.json ./
RUN npm ci --ignore-scripts

FROM ui-deps AS ui-source
COPY workspace_ui/management ./
# Run install scripts after the Quasar configuration is available.
RUN npm rebuild

FROM ui-source AS ui-test
RUN apk add --no-cache bash rsync
COPY workspace_ui/luigi-shell /ui/luigi-shell
COPY workspace_ui/build_dist.sh /ui/build_dist.sh
RUN npm test && npm run lint

FROM ui-source AS ui-builder
RUN npm run build && test -f dist/index.html
COPY workspace_ui/luigi-shell /ui/luigi-shell
RUN test -f /ui/luigi-shell/ui.html

FROM scratch AS ui-dist
COPY --from=ui-builder /ui/luigi-shell/ /
COPY --from=ui-builder /ui/management/dist/ /management/

FROM python:3.12.16-slim-trixie@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    prometheus_multiproc_dir=/var/tmp/prometheus_multiproc_dir \
    UI_DIST_DIR=/home/app/static \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends ca-certificates media-types \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p "$prometheus_multiproc_dir" "$UI_DIST_DIR"

RUN groupadd -g 1000 app && useradd -mr -d /home/app -s /bin/bash -u 1000 -g 1000 app

FROM runtime-base AS runtime
ARG VERSION
LABEL version=${VERSION}

COPY --from=api-builder /opt/venv /opt/venv

COPY --from=ui-dist --chown=app:app / ${UI_DIST_DIR}/
COPY workspace_ui/management/package.json workspace_ui/management/package-lock.json /usr/share/workspace-api/frontend/

COPY resources/gunicorn.conf.py /etc/gunicorn.conf.py

RUN chown -R app:app "$prometheus_multiproc_dir"
USER 1000:1000
WORKDIR /home/app

EXPOSE 8181
CMD ["gunicorn", "--config", "/etc/gunicorn.conf.py"]
