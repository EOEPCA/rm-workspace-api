# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import time
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette_exporter import PrometheusMiddleware, handle_metrics  # type: ignore[import-not-found]

from workspace_api import config

app = FastAPI(title="Workspace API")
templates = None

app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)


def get_dist_dir() -> Path | None:
    if (p := os.getenv("UI_DIST_DIR")) and Path(p).exists():
        return Path(p)

    dist_dir = Path(__file__).resolve().parents[1] / "workspace_ui" / "dist"
    if dist_dir.exists():
        return dist_dir
    return None


# Conditionally mount the built Vue app only if UI_MODE is "ui"
# and we are not using a remote frontend dev server.
if config.UI_MODE == "ui":
    dist_dir = get_dist_dir()

    if config.FRONTEND_URL.startswith("/ui"):
        if dist_dir is None:
            logging.getLogger(__name__).warning(
                f"UI_MODE is 'ui', but the dist directory '{dist_dir}' was not found. "
                "The UI will not be served. Did you forget to build the frontend?"
            )
        else:
            templates = Jinja2Templates(directory=dist_dir)
            app.mount("/ui", StaticFiles(directory=dist_dir, html=True))
    else:
        # for development server mount luigi-shell to /ui to serve luigi
        BASE_API_DIR = os.path.dirname(os.path.abspath(__file__))
        ui_luigi_dir = os.path.abspath(os.path.join(BASE_API_DIR, "..", "workspace_ui", "luigi-shell"))
        templates = Jinja2Templates(directory=ui_luigi_dir)
        app.mount("/ui", StaticFiles(directory=ui_luigi_dir, html=True))


if __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message).1000s",
        level=gunicorn_logger.level,
        handlers=gunicorn_logger.handlers,
    )
    logging.getLogger("kubernetes").setLevel(logging.INFO)
    logging.getLogger("kubernetes.client.rest").setLevel(logging.INFO)


@app.get("/probe")
def probe() -> dict[str, Any]:
    return {}


@app.get("/debug", include_in_schema=False)
def debug(request: Request) -> dict[str, Any]:
    return {
        "scheme": request.url.scheme,
        "baseurl": str(request.base_url),
        "headers": dict(request.headers.items()),
    }


@app.middleware("http")
async def log_middle(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    start_time = time.time()

    response = await call_next(request)

    ignored_paths = ["/probe", "/metrics"]
    if request.url.path not in ignored_paths:
        # NOTE: swagger validation failures prevent log_start_time from running
        duration = time.time() - start_time
        logging.info(
            f"{request.method} {request.url} "
            f"duration:{duration * 1000:.2f}ms "
            f"content_length:{response.headers.get('content-length')} "
            f"status:{response.status_code}"
        )

    return response


import_module("workspace_api.views")
