# Workspace v2

A FastAPI backend (workspace_api) and Quasar/Vue frontend (workspace_ui) for managing Workspace custom resources on Kubernetes clusters, such as the EOEPCA demo cluster.

## Table of Contents

- [Structure](#structure)
- [Requirements](#requirements)
- [Environment setup](#environment-setup)
- [Development workflow](#development-workflow)
  - [Run the API](#run-the-api)
  - [Frontend (Quasar/Vue)](#frontend-quasarvue)
  - [Linting and formatting](#linting-and-formatting)
  - [Testing](#testing)
  - [Developer tools](#developer-tools)
- [Configuration](#configuration)
- [Docker](#docker)
- [License](#license)

## Structure

- **Workspace API** — `workspace_api/` (Python FastAPI backend)
- **Workspace UI** — `workspace_ui/` (Quasar/Vue app; built assets placed in `workspace_ui/dist/`)

## Requirements

- Python **3.12** (e.g., via [pyenv](https://github.com/pyenv/pyenv))
- [uv](https://github.com/astral-sh/uv) for Python deps
- Node.js **20.x** + npm for the frontend
- Docker (optional)

## Environment setup

1. Backend setup (from repo root):

   ```bash
   cd workspace_api
   pyenv local 3.12.6
   python --version   # should be 3.12.6
   uv lock --python python
   uv sync --python python --extra dev
   uv run pre-commit install
   ```

2. Frontend setup (from repo root):

   ```bash
   cd workspace_ui
   npm ci
   ```

## Development workflow

### Run the API

From the `workspace_api/` folder:

```bash
KUBECONFIG=~/.kube/config-eoepca-demo uv run env PYTHONPATH=.. uvicorn workspace_api:app --reload --host=0.0.0.0 --port=5000 --log-level=info
```

The API will be at <http://localhost:5000>.

### Frontend (Quasar/Vue)

You can develop the UI in two ways: **dev server** (hot reload) or **production build** served by the backend/static files.

#### A) Dev server (hot reload)

Run the Quasar/Vite dev server (default: <http://localhost:9000>):

From the `workspace_ui/vue-app/` folder:

```bash
npm run dev
```

Then in another terminal, run the backend pointing to the dev server:

From the `workspace_api/` folder:

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" FRONTEND_URL="http://localhost:9000" uv run env PYTHONPATH=.. uvicorn workspace_api:app --reload --host=0.0.0.0 --port=5000 --log-level=info
```

Open `http://localhost:5000/workspaces/<YOUR_WS_NAME>` in a browser (sends `Accept: text/html`) to load the UI via the dev server.

#### B) Production build (no dev server)

Build the SPA into `workspace_ui/dist/` and let the backend serve it as static content:

From the `workspace_ui/vue-app/` folder:

```bash
npm run build
```

Now start the backend in **UI mode** pointing to the static path (mounted at `/ui`):

From the `workspace_api/` folder:

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" FRONTEND_URL="/ui" uv run env PYTHONPATH=.. uvicorn workspace_api:app --reload --host=0.0.0.0 --port=5000 --log-level=info
```

> The Docker image (below) builds the UI and copies `workspace_ui/dist/` into the container at `/home/app/static`.

### Linting and formatting

Python (from `workspace_api/`):

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

Frontend (from `workspace_ui/`), if you have lint scripts defined:

```bash
npm run lint
```

Run all pre-commit hooks from repo root:

```bash
uv run pre-commit run --all-files
```

### Testing

Backend tests live in `workspace_api/tests/`:

```bash
cd workspace_api
uv run pytest
```

Watch mode:

```bash
uv run pytest-watcher tests --now
```

## Developer tools

Installed via the backend `dev` extra:

- **mypy** – static typing
- **ruff** – linting & formatting
- **pytest / pytest-watcher** – testing
- **pre-commit** – git hooks
- **ipdb** – debugger

Run via `uv run <tool>` from `workspace_api/`.

## Configuration

Environment variables used by the backend:

| Variable | Default | Description |
| --- | --- | --- |
| `PREFIX_FOR_NAME` | `"ws"` | Prefix used when generating Kubernetes workspace names from user input. |
| `WORKSPACE_SECRET_NAME` | `"workspace"` | Name of the Kubernetes `Secret` that holds per-workspace storage credentials. |
| `CONTAINER_REGISTRY_SECRET_NAME` | `"container-registry"` | Name of the Kubernetes `Secret` that holds per-workspace container registry credentials. |
| `UI_MODE` | `"no"` | Set to `"ui"` to enable serving the frontend (templated HTML + SPA). |
| `FRONTEND_URL` | `"/ui"` | Base path (production) or absolute URL (dev server) for the frontend. Use `http://localhost:9000` with the dev server. |

## Docker

Build the combined image (Python **3.12.6** + built UI) from repo root:

```bash
docker build . -t workspace-api:latest --build-arg VERSION=$(git rev-parse --short HEAD)
```

Run it:

```bash
docker run --rm --p 8080:8080 --name workspace-api workspace-api:latest
```

## License

[Apache 2.0](LICENSE) (Apache License Version 2.0, January 2004)
<https://www.apache.org/licenses/LICENSE-2.0>
