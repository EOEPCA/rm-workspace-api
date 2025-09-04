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
