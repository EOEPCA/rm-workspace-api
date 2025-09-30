# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os
from multiprocessing import cpu_count
from typing import Any

from prometheus_client import multiprocess


def child_exit(_server: Any, worker: Any) -> None:
    multiprocess.mark_process_dead(worker.pid)


daemon = False
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8080")
_workers_default = str(2 * cpu_count())
workers = int(os.environ.get("GUNICORN_WORKERS", _workers_default))
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker")
worker_connections = int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", "1000"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
wsgi_app = os.environ.get("GUNICORN_APP", "workspace_api:app")
