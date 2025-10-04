# Workspace API & UI Layer

This layer provides a **Kubernetes-native control plane** for collaborative, data-driven workspaces.
It combines a **FastAPI backend (`workspace_api`)** with a **Quasar/Vue frontend (`workspace_ui`)** to deliver a seamless management layer on top of Kubernetes Custom Resources.

At its core, the Workspace API & UI Layer orchestrates three pillars:

- **Memberships** — define who belongs to a workspace and what role they hold.
- **Storage** — provision buckets, attach credentials, and manage access grants between workspaces.
- **Interactive Sessions** — track and control whether interactive workspace sessions are running (always-on) or can be started (on-demand), respectively.

By building on Kubernetes CRDs (`Storage`, `Datalab`), the API exposes a clean **HTTP/JSON interface** and an optional **single-page UI** to manage these resources without needing to interact directly with `kubectl`.  This makes it equally suited for **operators** (who want Kubernetes-level control) and **end users** (who just need to join a workspace, get storage, and start analyzing data).

**Kubernetes-native:** The Workspace API sits on top of two CRDs — **Storage** and **Datalab** — and reads and patches them to present a unified “Workspace” view (including storage, memberships, and session state).  It applies changes through standard REST calls, simplifying access and abstracting away the low-level details of the CRDs and Kubernetes.

See: [Storage CRD](https://provider-storage.versioneer.at/latest/reference-guides/api/) · [Datalab CRD](https://provider-datalab.versioneer.at/latest/reference-guides/api/)

## Table of Contents

- [Structure](#structure)
- [Requirements](#requirements)
- [Environment setup](#environment-setup)
- [Development workflow](#development-workflow)
- [Configuration](#configuration)
- [Docker](#docker)
- [License](#license)

## Structure

- **Workspace API** — `workspace_api/` (FastAPI backend)
- **Workspace UI** — `workspace_ui/` (Quasar/Vue app; built assets placed in `workspace_ui/dist/`)
  - **Luigi Shell** — provides the micro frontend navigation and layout
  - **Management app** — a single-page application (SPA) embedded via Luigi as a view, using Quasar.js/Vue

### Directory layout

```bash
.
├── workspace_api/                # Python FastAPI backend
└── workspace_ui/                 # Luigi shell + Vue frontend views
    ├── luigi-shell/
    │   ├── ui.html               # Luigi shell template (rendered by FastAPI)
    │   ├── logo.svg              # Main logo
    │   ├── icons/                # favicon.ico
    │   └── standalone/           # Luigi shell with statically defined workspace data
    ├── management/               # Quasar App
    │   ├── index.html            # Vue app entry point (used inside Luigi iframe)
    │   └── dist/                 # Built Quasar App
    └── dist/                     # Combined built UI code, served as static content
```

## Requirements

- Python **3.12** (e.g., via [pyenv](https://github.com/pyenv/pyenv))
- [uv](https://github.com/astral-sh/uv) for Python deps
- Node.js **20.x** + npm for the frontend
- Docker (optional)

## Environment setup

1. Backend setup (from repo root):

   ```bash
   pyenv local 3.12.6
   python --version   # should be 3.12.6
   uv lock --python python
   uv sync --python python --extra dev
   uv run pre-commit install
   ```

2. Frontend setup (from repo root):

   ```bash
   cd workspace_ui
   ./build_dist.sh
   cd ..
   ```

## Development workflow

### Run backend only

```bash
KUBECONFIG=~/.kube/config-eoepca-demo uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8080 --log-level=info
```

The API will be at <http://localhost:8080>.

### Run backend API and Frontend UI

#### A) Dev server mode (hot reload)

Run the Quasar/Vite dev server (default: <http://localhost:9000>):

From the `workspace_ui/management` folder:

```bash
npm run dev
```

Then in another terminal, from the `workspace_api/` folder:

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" FRONTEND_URL="http://localhost:9000" uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8080 --log-level=info
```

Open `http://localhost:8080/workspaces/<YOUR_WS_NAME>` in a browser (sends `Accept: text/html`) to load the UI via the dev server.

#### B) Production mode (no dev server)

Build the SPA into `workspace_ui/dist/` and let the backend serve it as static content:

From the `workspace_ui/` folder:

```bash
./build_dist.sh
```

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8080 --log-level=info
```

> The Docker image (below) builds both the API and the UI and copies `workspace_ui/dist/` into the container.

### Linting and formatting

Python (from `workspace_api/`):

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

Management Frontend (from `workspace_ui/management`):

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

### Developer tools

Installed via the backend `dev` extra:

- **mypy** – static typing
- **ruff** – linting & formatting
- **pytest / pytest-watcher** – testing
- **pre-commit** – git hooks
- **ipdb** – debugger

Run via `uv run <tool>` from `workspace_api/`.

## Configuration

Environment variables used by the backend (besides `KUBECONFIG` for Kubernetes access):

| Variable | Default | What it does |
|---|---|---|
| `PREFIX_FOR_NAME` |  | Prefix applied to user-facing names to build K8s object names (e.g. `ws` to get `ws-alice` for `alice`). |
| `USE_VCLUSTER` | `false` |  Whether to provision an isolated vcluster for each datalab session (`true`) or run in separate namespace on host cluster (`false`). |
| `SESSION_MODE` | `on` | Whether sessions can be started on-demand with automatic shutdown (`auto`) or are always on (`on`) or off (`off`). |
| `STORAGE_SECRET_NAME` | `<principal>` | Name template for the secret that contains S3 credentials for the workspace. |
| `CONTAINER_REGISTRY_SECRET_NAME` | `<principal>` | Name template for the secret holding per-workspace container registry (OCI) credentials. |
| `ENDPOINT` | from `AWS_ENDPOINT_URL` | S3 endpoint URL used when falling back to environment-based config. |
| `REGION` | from `AWS_REGION` or `AWS_DEFAULT_REGION` | S3 region used when falling back to environment-based config. |
| `UI_MODE` | `no` | Set to `ui` to enable templated HTML shell and SPA embedding. |
| `FRONTEND_URL` | `/ui/management` | Base path (prod) or absolute URL (dev server like `http://localhost:9000`) for the SPA. |

## Docker

Build the combined image (Python **3.12.6** + built UI) from repo root:

```bash
docker build . -t workspace-api:latest --build-arg VERSION=$(git rev-parse --short HEAD)
```

Run it:

```bash
docker run --rm -p 8080:8080   -e GUNICORN_WORKERS=2   -e UI_MODE=ui   -e KUBECONFIG=/kube/config   --mount type=bind,src=$HOME/.kube/config-eoepca-demo,dst=/kube/config,readonly   workspace-api:latest
```

## License

[Apache 2.0](LICENSE) (Apache License Version 2.0, January 2004)
<https://www.apache.org/licenses/LICENSE-2.0>
