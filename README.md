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
  - apiGroups: [""]
    resources: ["persistentvolumeclaims", "resourcequotas"]
    verbs: ["list"]
```

The `persistentvolumeclaims` and `resourcequotas` ClusterRole rule is optional. Without it, workspace details still load, but the API omits `resource_usage` and the UI hides the Persistent storage section.

These permissions enable the API to **synchronize resource state** and **discover CRD schemas** while maintaining namespace isolation and least privilege.

## Session Operation Modes

There are three modes that define how the API initializes the default Datalab session for a newly created team:

- **Disabled (`SESSION_MODE=off`)** — The API creates the `Datalab` resource without declaring a default session. The workspace is primarily used to provision storage buckets and manage bucket access. Operators can still manage sessions directly on the corresponding `Datalab` Custom Resource.

- **Always On (`SESSION_MODE=on`)** — The API declares the default Datalab session with state `started` during workspace provisioning. Operators can manually patch the `Datalab` resource in the cluster to stop or restart the session if required.

- **On Demand (`SESSION_MODE=auto`)** — The API declares the default Datalab session with state `stopped`. The Workspace UI exposes a Datalab link that starts the session by patching it to `started` when a team needs access. Operators can define external policies for automatic shutdowns of sessions (for example, every day at 8 p.m. or every Friday night). When a team needs access again, they can relaunch the session via the Datalab link in the Workspace UI.

**Note:**
The Workspace UI can manage multiple sessions per team. By default, up to three sessions may be declared; operators can change this with `MAX_SESSIONS`.

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
KUBECONFIG=~/.kube/config-eoepca-demo uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8181 --log-level=info
```

The API will be at <http://localhost:8181>.

### Run backend API and Frontend UI

#### A) Dev server mode (hot reload)

Run the Quasar/Vite dev server (default: <http://localhost:9000>):

From the `workspace_ui/management` folder:

```bash
npm run dev
```

Then in another terminal, from the `workspace_api/` folder:

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" FRONTEND_URL="http://localhost:9000" uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8181 --log-level=info
```

Open `http://localhost:8181/workspaces/<YOUR_WS_NAME>` in a browser (sends `Accept: text/html`) to load the UI via the dev server.

#### B) Production mode (no dev server)

Build the SPA into `workspace_ui/dist/` and let the backend serve it as static content:

From the `workspace_ui/` folder:

```bash
./build_dist.sh
```

```bash
KUBECONFIG=~/.kube/config-eoepca-demo UI_MODE="ui" uv run uvicorn workspace_api:app --reload --host=0.0.0.0 --port=8181 --log-level=info
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

The Workspace API uses a **gateway-centric authentication model**. Authentication is enforced upstream by an API gateway (for example APISIX) using OpenID Connect. The gateway validates the access token signature, issuer, expiration, and other token policy. Only authenticated requests are forwarded to the backend.

The backend **does not re-validate tokens cryptographically**. It treats the forwarded token as trusted input, requires the decoded `aud` claim to contain `AUTH_AUDIENCE` (default `workspace-api`), and extracts a minimal identity and authorization context, which is attached to each request via `request.state.user`. It does not enforce `azp` or `client_id` itself.

Backend JWT handling checks only the forwarded token shape and authorization claims:

- `Authorization` header exists and uses `Bearer <token>`.
- JWT payload can be decoded.
- `aud` is either a string equal to `AUTH_AUDIENCE` or a list containing it.
- `resource_access` is mapped to permissions:
  - `workspace-api:admin` -> wildcard admin
  - `<workspace>:ws_admin` -> admin permissions
  - `<workspace>:ws_access` -> read/session visibility permissions
  - `<workspace>:ws_api` -> bucket credential visibility only

The gateway remains responsible for signature validation, issuer validation, expiration/`nbf`, token policy, client trust, and OIDC/JWKS handling. The backend does not enforce `azp` or `client_id`; `resource_access` still says what the caller may do.

External roles are normalized into explicit permissions:

- **`ws_access`**
  - `VIEW_BUCKET_CREDENTIALS`
  - `VIEW_MEMBERS`
  - `VIEW_BUCKETS`
  - `VIEW_RESOURCE_USAGE`
  - `VIEW_STORES`
  - `VIEW_SESSIONS`

- **`ws_api`**
  - `VIEW_BUCKET_CREDENTIALS`

- **`ws_admin`**
  - all `ws_access` permissions, plus:
  - `ISSUE_TOKENS`
  - `MANAGE_MEMBERS`
  - `MANAGE_BUCKETS`
  - `MANAGE_STORES`
  - `MANAGE_SESSIONS`

Authorization decisions are based exclusively on these permissions, not on raw roles.

The `ws_api` role is intended for workspace-local machine/API access, for example a Keycloak client-credentials token minted from a provider-datalab-generated confidential workspace client. It currently grants only bucket credential visibility and deliberately does not grant session, member, bucket, or store management permissions.

Workspace API does not evaluate Keycloak role-scope mappings. It only authorizes the roles present in the token's `resource_access` claim, so a client-credentials token is treated as machine/API access only when it carries `ws_api`.

The platform-wide `workspace-api` client remains separate: its `admin` role grants wildcard workspace administration. A token requested through a workspace client such as `ws-bob` is accepted by the backend only when its audience is valid for Workspace API; a token intended only for the workspace runtime must not be forwarded to this backend.

### Workspace Token Issuing

`GET /workspaces/{workspace_name}/token` exchanges the workspace OAuth client secret from the Kubernetes secret `{workspace_name}-oauth-client` for a client-credentials access token. The caller must present a token whose `aud` contains `AUTH_AUDIENCE` and either be global admin or have `ws_admin` permissions for the requested workspace.

The broker requests a client-credentials token for `AUTH_AUDIENCE` from `TOKEN_BROKER_TOKEN_ENDPOINT`. It returns only `access_token`, `token_type`, `expires_in`, and `scope` with `Cache-Control: no-store`, and rejects tokens that lack the expected audience or the requested workspace's `ws_api` role.

The expected secret can contain direct keys:

```json
{
  "clientID": "ws-bob",
  "clientSecret": "<client-secret>"
}
```

or one JSON-encoded secret value with those fields. Accepted client id keys are `clientID`, `client_id`, and `CLIENT_ID`; accepted client secret keys are `clientSecret`, `client_secret`, and `CLIENT_SECRET`. The broker authenticates with `client_secret_basic`.

When `AUTH_MODE=no`, authentication is disabled. The backend injects a synthetic user context with username `Default` and wildcard workspace permissions granting full access.

### Example Access Token Claims

Human Workspace API/UI access normally uses a token requested through the `workspace-api` client. The token can contain workspace-local roles for the workspaces the user may access:

```json
{
  "aud": ["workspace-api"],
  "azp": "workspace-api",
  "sub": "user-id-alice",
  "preferred_username": "alice",
  "resource_access": {
    "ws-alice": {
      "roles": ["ws_admin"]
    },
    "ws-bob": {
      "roles": ["ws_access"]
    },
    "ws-ci": {
      "roles": ["ws_api"]
    }
  }
}
```

Workspace-local automation can use a client-credentials token requested through the confidential workspace client, provided the token audience is valid for Workspace API. The request authenticates the `ws-bob` client itself; `preferred_username` is added by Keycloak from the service-account user and is usually `service-account-ws-bob`.

```bash
curl -sS -X POST \
  "https://<keycloak>/realms/<realm>/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=ws-bob" \
  --data-urlencode "client_secret=<client-secret>"
```

```json
{
  "aud": ["workspace-api"],
  "azp": "ws-bob",
  "sub": "<keycloak-service-account-user-id>",
  "preferred_username": "service-account-ws-bob",
  "resource_access": {
    "ws-bob": {
      "roles": ["ws_api"]
    }
  }
}
```

For development or testing purposes, similar payloads can be encoded as JWTs and passed via the `Authorization` header as Bearer tokens when `AUTH_MODE=gateway`.

## Configuration

Environment variables used by the backend (besides `KUBECONFIG` for Kubernetes access):

| Variable | Default | What it does |
|---|---|---|
| `PREFIX_FOR_NAME` |  | Prefix applied to user-facing names to build K8s object names (e.g. `ws` to get `ws-alice` for `alice`). |
| `PROVIDER_ENVIRONMENT` | `datalab` | EnvironmentConfig name selected for new provider-storage and provider-datalab XRs. The API writes this value to `storages.pkg.internal/environment` on `Storage` and `datalabs.pkg.internal/environment` on `Datalab`. |
| `USE_VCLUSTER` | `false` |  Whether to provision an isolated vcluster for each datalab session (`true`) or run in separate namespace on host cluster (`false`). |
| `SESSION_MODE` | `on` | Initial default-session mode for newly created Datalabs: `on` declares it as `started`, `auto` declares it as `stopped` for UI launch, and `off` does not declare it. |
| `MAX_SESSIONS` | `3` | Maximum number of Datalab sessions that can be declared for a workspace. |
| `DISABLE_DOCKER_REGISTRY` | `false` | By default, each datalab gets an in-session Docker registry. |
| `DISABLE_STORES` | `false` | Disable creation and display of all Datalab store types. |
| `DISABLED_STORE_TYPES` |  | Comma- or semicolon-separated store types to disable even when their backing CRDs are installed. Accepted aliases include `postgres`, `qdrant`, `redis`, and `mongodb`. |
| `ENDPOINT` | from `AWS_ENDPOINT_URL` | S3 endpoint URL used when falling back to environment-based config. |
| `REGION` | from `AWS_REGION` or `AWS_DEFAULT_REGION` | S3 region used when falling back to environment-based config. |
| `UI_MODE` | `no` | Set to `ui` to enable templated HTML shell and SPA embedding. |
| `FRONTEND_URL` | `/ui/management` | Base path (prod) or absolute URL (dev server like `http://localhost:9000`) for the SPA. |
| `AUTH_MODE` | `gateway` | Authentication mode `gateway` expects a validated `Authorization: Bearer <access_token>` header to be forwarded by an upstream gateway, `no` disables authentication entirely (for local development only). |
| `AUTH_AUDIENCE` | `workspace-api` | Required JWT `aud` value when `AUTH_MODE=gateway`. The decoded `aud` may be a string or list, but it must contain this value. |
| `AUTH_DEBUG` | `false` | Enable verbose authentication and workspace debug logging. |
| `TOKEN_BROKER_TOKEN_ENDPOINT` |  | OAuth/OIDC token endpoint used by `GET /workspaces/{workspace_name}/token`. Required for the broker endpoint. |
| `TOKEN_BROKER_TIMEOUT_SECONDS` | `10` | Timeout for the outbound token endpoint request. |

### Store creation

The Workspace UI only offers store types that the cluster can currently reconcile. A store type is available when:

- the `Datalab` CRD exposes the matching spec field,
- the backing operator CRD is installed in the cluster, and
- the store type is not disabled through `DISABLE_STORES` or `DISABLED_STORE_TYPES`.

The current store type mapping is:

| Store type | Datalab field | Required backing CRD |
|---|---|---|
| Database (Postgres) | `spec.databases` | `postgresclusters.postgres-operator.crunchydata.com` |
| Vector store (Qdrant) | `spec.vectorStores` | `qdrantclusters.qdrant.io` |
| Cache (Redis) | `spec.cacheStores` | `redis.redis.redis.opstreelabs.in` |
| Document store (MongoDB) | `spec.documentStores` | `mongodbcommunity.mongodbcommunity.mongodb.com` |

If a backing CRD is not installed, the UI hides that store type and the API rejects attempts to create it. Manual changes made directly to a `Datalab` XR are not blocked by the Workspace API; in that case Crossplane reports reconciliation failures on the `Datalab` status if the required operator CRD is missing.

## Docker

Build the combined image (Python **3.12.11** + built UI) from repo root:

```bash
docker build . -t workspace-api:latest --build-arg VERSION=$(git rev-parse --short HEAD)
```

Run it, e.g.

```bash
docker run --rm \
   -p 8181:8181 \
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
