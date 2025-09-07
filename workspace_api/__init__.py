# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

app = FastAPI()
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
    templates = Jinja2Templates(directory=dist_dir)

    if config.FRONTEND_URL == "/ui":
        if dist_dir is None:
            logging.getLogger(__name__).warning(
                f"UI_MODE is 'ui', but the dist directory '{dist_dir}' was not found. "
                "The UI will not be served. Did you forget to build the frontend?"
            )
        else:
            app.mount("/ui", StaticFiles(directory=dist_dir, html=True))
    else:
        # for development server mount public to /ui to serve static files
        BASE_API_DIR = os.path.dirname(os.path.abspath(__file__))
        ui_public_dir = os.path.abspath(os.path.join(BASE_API_DIR, "..", "workspace_ui", "public"))
        app.mount("/ui", StaticFiles(directory=ui_public_dir, html=True))


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
