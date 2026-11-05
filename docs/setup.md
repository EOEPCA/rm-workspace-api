# Setup and development

## Workspaces and providers

Workspace API uses Provider Storage for buckets and bucket access, and
Provider Datalab for members, data services, sessions, and service credentials.
Either provider can be used alone. The API manages their `Storage` and `Datalab`
Kubernetes resources.

Set `DISABLE_STORAGE=true` or `DISABLE_DATALAB=true` to disable a provider.
These settings take priority over cluster discovery. The API hides its
features and keeps existing cluster resources. Creation and deletion use the
enabled providers. Creating a workspace returns 503 when neither is available;
reading a missing workspace returns 404.

`GET /status` reports health and provider availability. A missing or disabled
provider does not make the API unhealthy. The UI hides features whose
provider or workspace resource is unavailable. Store types appear only when
enabled in configuration and supported by the provider schema and backing
operator.

For `DISABLED_STORE_TYPES`, use `database`, `cache`, or `document`,
separated by commas. Use `DISABLE_STORES=true` to disable all stores.

### Browser sessions

`SESSION_MODE` controls the initial default session: `on` starts it, `auto`
creates it stopped, and `off` creates none. Start and stop sessions on the
Sessions page. `MAX_SESSIONS` limits the number of declared sessions per workspace.

Start a session and wait until it is ready before selecting **Open session**.
Refresh the page to check progress. Management lists configured sessions that
can be changed or deleted. Workspace navigation lists ready sessions.

## Access

An OpenID Connect gateway must verify token signatures, issuer, and expiry.
The API checks the audience and workspace roles in the forwarded Bearer token.
Keep it behind the gateway when `AUTH_MODE=gateway`. Use `AUTH_MODE=no` only
for local development.

| Token role | Access |
| --- | --- |
| `workspace-api:admin` | All workspaces and token requests |
| `<workspace>:ws_admin` | Workspace management, credentials, and token requests |
| `<workspace>:ws_access` | Workspace details, sessions, and service and OAuth2 credentials |
| `<workspace>:ws_api` | Service credentials |

The API needs these Kubernetes permissions in the namespaces it manages:

| Resources | Verbs |
| --- | --- |
| Storage and Datalab resources | `get`, `list`, `create`, `patch`, `delete` |
| Referenced Secrets | `get` in each referenced namespace |
| Provider and backing store CRDs | `get` |
| Workspace PVCs and ResourceQuotas | `list` |

PVC and quota access is optional. Without it, the UI omits storage usage.

## Development

Use Python 3.12, `uv`, and `npm`. Run backend commands from the repo root.

```bash
uv sync --extra dev
uv run pre-commit install
KUBECONFIG=/path/to/config uv run uvicorn workspace_api:app --reload --port=8181
```

For UI development, run `npm run dev` in `workspace_ui/management`. Start the
backend with `UI_MODE=ui` and `FRONTEND_URL=http://localhost:9000`. Open
`http://localhost:8181/workspaces/<workspace-name>`.

For a sample UI without a backend, run `npm run shell+dev` in
`workspace_ui/management` and open `http://localhost:8181`. Changes need a
backend; the sample data is in `workspace_ui/luigi-shell/standalone/config/app-config.js`.

To serve built assets, run `workspace_ui/build_dist.sh`, then start the backend
with `UI_MODE=ui`. The build keeps the previous bundle until the new one is
ready. Rebuild after UI changes. Startup fails if the required UI files are
missing.

Run the backend checks from the repo root:

```bash
uv run pytest workspace_api/tests
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pre-commit run --all-files
```

Run the frontend checks in `workspace_ui/management`:

```bash
npm test
npm run lint
npm run build
```

Backend tests mock Kubernetes. Use an isolated test cluster to check a live
provider installation.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PREFIX_FOR_NAME` | Empty | Prefix for workspace resource names. |
| `PROVIDER_ENVIRONMENT` | `datalab` | EnvironmentConfig annotation on new resources. |
| `DISABLE_STORAGE` | `false` | Disable Storage and hide its features. |
| `DISABLE_DATALAB` | `false` | Disable Datalab and hide its features. |
| `USE_VCLUSTER` | `false` | Add a virtual cluster named `vc0` to new workspaces. |
| `SESSION_MODE` | `on` | Initial default session: `on`, `auto`, or `off`. |
| `MAX_SESSIONS` | `3` | Limit on declared sessions per workspace. |
| `DISABLE_STORES` | `false` | Hide and reject all store types. |
| `DISABLED_STORE_TYPES` | Empty | Comma-separated names: `database`, `cache`, `document`. |
| `UI_MODE` | `no` | Set to `ui` to serve the UI. |
| `FRONTEND_URL` | `/ui/management` | Built UI path or development server URL. |
| `AUTH_MODE` | `gateway` | Use gateway tokens; `no` disables authentication. |
| `AUTH_AUDIENCE` | `workspace-api` | Required token audience. |
| `AUTH_DEBUG` | `false` | Enable authentication debug logs. |
| `TOKEN_BROKER_TIMEOUT_SECONDS` | `10` | Timeout for each discovery or token request, in seconds. |

## Docker

The image includes the backend and built UI:

```bash
docker build . -t workspace-api
```

Run it with a mounted kubeconfig or a Kubernetes ServiceAccount. Set
`UI_MODE=ui` to serve the UI, and expose port 8181.
