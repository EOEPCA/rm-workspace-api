import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette_exporter import PrometheusMiddleware, handle_metrics

app = FastAPI()

app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

BASE_API_DIR = os.path.dirname(os.path.abspath(__file__))
UI_SOURCE_DIR = os.path.abspath(os.path.join(BASE_API_DIR, "..", "workspace_ui"))
VUE_DIST_DIR = os.path.abspath(os.path.join(BASE_API_DIR, "..", "workspace_ui", "dist"))
templates = Jinja2Templates(directory=UI_SOURCE_DIR)
# app.mount("/ui_public", StaticFiles(directory=os.path.join(UI_SOURCE_DIR, "public")), name="ui_public_assets")
app.mount("/ui", StaticFiles(directory=VUE_DIST_DIR, html=True), name="ui_dist_assets")

# TODO: set up, make sure that multiple processes are handled

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
def probe():
    return {}


@app.middleware("http")
async def log_middle(request: Request, call_next):
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


import workspace_api.views  # noqa
