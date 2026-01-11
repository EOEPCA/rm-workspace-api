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

## Kubernetes RBAC Requirements

As the Workspace API runs directly on Kubernetes, the **ServiceAccount** executing it requires minimal **RBAC (Role-Based Access Control)** permissions to operate on resources such as `secrets`, `storages`, and `datalabs`.
These permissions allow the service to list, watch, and modify Custom Resources within its namespace and to read their CRD definitions.

Both a **Role** and **ClusterRole** are automatically provisioned through the [Helm chart](https://github.com/EOEPCA/helm-charts-dev/tree/main/charts/rm-workspace-api).

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["pkg.internal"]
    resources: ["storages", "datalabs"]
    verbs: ["*"]

---

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
rules:
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get"]
    resourceNames: ["storages.pkg.internal", "datalabs.pkg.internal"]
```

These permissions enable the API to **synchronize resource state** and **discover CRD schemas** while maintaining namespace isolation and least privilege.

## Session Operation Modes

There are three modes that define how the Datalab session for a team is managed:

- **Disabled (`SESSION_MODE=off`)** — The Datalab is generally disabled. Only the operator can manually patch the corresponding `Datalab` Custom Resource in the cluster to start a session for a team. In this mode, the workspace is primarily used to provision storage buckets and manage bucket access.

- **Always On (`SESSION_MODE=on`)** — The Datalab session is automatically started during workspace provisioning and remains continuously active. Only the operator can manually patch the `Datalab` resource in the cluster to stop (and restart) the session if required.

- **On Demand (`SESSION_MODE=auto`)** — The Datalab session can be started by a team directly through the Workspace UI whenever needed. The operator can define policies for automatic shutdowns of sessions (for example, every day at 8 p.m. or every Friday night). When a team needs access again, they can simply relaunch the session via the Datalab link in the Workspace UI. Examples for configuring time-based shutdown policies are provided in the documentation respectivly can be found on the demo cluster.

**Note:**
At the moment, there is only one (“default”) session per team. Operators can manually start additional sessions via the corresponding `Datalab` Custom Resource in the cluster, but multi-session support per team is not yet officially available and is considered experimental.

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
   pyenv local 3.12.11
   python --version   # should be 3.12.11
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

## Authentication and Authorization

The Workspace API uses a **gateway-centric authentication model**. Authentication is enforced upstream by an API gateway (for example APISIX) using OpenID Connect. The gateway validates the access token (signature, issuer, audience, expiration). Only authenticated requests are forwarded to the backend.

The backend **does not re-validate tokens cryptographically**. Instead, it treats the token as trusted input and extracts a minimal identity and authorization context, which is attached to each request via `request.state.user`.

Internally, the API retains only:

- the username (`preferred_username`)
- a workspace-to-permissions mapping derived from the token’s `resource_access` claim

External roles are normalized into explicit permissions:

- **`ws_access`**
  - `VIEW_BUCKET_CREDENTIALS`
  - `VIEW_MEMBERS`
  - `VIEW_BUCKETS`
  - `VIEW_DATABASES`

- **`ws_admin`**
  - all of the above, plus:
  - `MANAGE_MEMBERS`
  - `MANAGE_BUCKETS`

Authorization decisions are based exclusively on these permissions, not on raw roles.

When `AUTH_MODE=no`, authentication is disabled. The backend injects a synthetic user context with username `Default` and wildcard workspace permissions granting full access.

### Example Access Token Claims for Development

The following JSON document is an example of claims that matches the expectations of the Workspace API. For development or testing purposes, this payload can be encoded as a JWT and passed via the `Authorization` header as a Bearer token.

```json
{
  "preferred_username": "alice",
  "resource_access": {
    "ws-alice": {
      "roles": ["ws_admin"]
    },
    "ws-bob": {
      "roles": ["ws_access"]
    }
  }
}
```

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
| `AUTH_MODE` | `gateway` | Authentication mode `gateway` expects a validated `Authorization: Bearer <access_token>` header to be forwarded by an upstream gateway, `no` disables authentication entirely (for local development only). |

## Docker

Build the combined image (Python **3.12.11** + built UI) from repo root:

```bash
docker build . -t workspace-api:latest --build-arg VERSION=$(git rev-parse --short HEAD)
```

Run it, e.g.

```bash
docker run --rm \
   -p 8080:8080 \
   -e GUNICORN_WORKERS=2 \
   -e UI_MODE=ui \
   -e PREFIX_FOR_NAME=ws \
   -e AWS_REGION=eoepca-demo \
   -e AWS_ENDPOINT_URL=https://minio.develop.eoepca.org \
   -e KUBECONFIG=/kube/config \
   --mount type=bind,src=$HOME/.kube/config-eoepca-demo,dst=/kube/config,readonly \
   workspace-api:latest
```

## License

[Apache 2.0](LICENSE) (Apache License Version 2.0, January 2004)
<https://www.apache.org/licenses/LICENSE-2.0>
