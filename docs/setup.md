# Setup and development

## Workspaces and providers

Workspace API uses Provider Storage for buckets and bucket access, and
Provider Datalab for members, data services, sessions, and service credentials.
Either provider can be used alone. The API manages their `Storage` and `Datalab`
Kubernetes resources.

Set `DISABLE_STORAGE=true` or `DISABLE_DATALAB=true` to disable a provider.
The API hides disabled features and keeps existing cluster resources. Install
each provider and its backing operators before you enable its features.

`GET /status` reports health and the `storage_enabled` and `datalab_enabled`
configuration flags. A missing or disabled provider does not make the API
unhealthy. The UI hides features whose provider or workspace resource is
unavailable.

Set `STORES` to a comma-separated list of `postgres`, `redis`, and `mongo`.
Values are case-insensitive. An empty value disables all stores. An unsupported
value stops startup with a configuration error.

New resource names use 1-30 lowercase letters, digits, or hyphens and start
and end with a letter or digit. Bucket names also require at least three characters.

### Workspace environments

With `UI_MODE=ui`, `/workspaces` opens the Quasar overview in the workspace
shell. Workspace API administrators can create and delete workspaces there.
For each installed provider, first select a composition. Then select an optional
configuration, or keep the default shown with the composition's name.
The name field shows the configured prefix as fixed text. Enter the name
after the prefix. A single available choice is read-only.

Compositions must target the provider's resource type and API version.
Configuration overrides need the label `storages.pkg.internal/name` for
Storage or `datalabs.pkg.internal/name` for Datalab. The label value does not
filter choices. A config can have both labels. The composition's own config
is excluded from overrides because it is already part of the defaults.
Override names can have up to 63 characters.

Creation always sets `spec.crossplane.compositionRef.name`. A custom override
sets `spec.environmentName` on that provider's XR. With no override, the API
omits this field so the composition can use its defaults. Each provider can
use a different composition and config. The API validates both selections
before it creates either resource. See the running API's `/docs` page for
request fields.

The providers merge `default`, the composition config, the selected override,
and a config named after the workspace, in that order. Later values replace
earlier values; nested maps keep fields that later configs do not set. Missing
configs are skipped. CloudFerro needs a config with its project and
`storage.providerConfigName`; select a project override when these settings
are absent from the composition defaults.

Custom overrides need provider CRDs and compositions that support
`spec.environmentName`.

### Browser sessions

`SESSION_MODE` controls the initial default session: `on` starts it, `auto`
creates it stopped, and `off` creates none. Start and stop sessions on the
Sessions page. `MAX_SESSIONS` limits the number of declared sessions per workspace.

Start a session and wait until it is ready before selecting **Open session**.
Refresh the page to check progress. Management lists configured sessions that
can be changed or deleted. Workspace navigation lists ready sessions.

The **Links** section shows browser endpoints from Datalab `status.endpoints`,
returned as `datalab.endpoints` by the API. Each link needs a `name`, a valid
HTTP or HTTPS `url`, and `ready: true`. The `data` endpoint appears as **Data**.
Missing, invalid, or unready entries add no links.

The overview shows total requested storage as **Persistent session storage**,
including stopped sessions. It is shown only when every session has a valid size.
Sizes come from Datalab `status.sessions[].pvcSize`, returned as
`datalab.sessions[].pvc_size`. A known zero size is `0`; an unknown size is omitted.

## Access

An OpenID Connect gateway must verify token signatures, issuer, and expiry.
The API checks the audience and workspace roles in the forwarded Bearer token.
Keep it behind the gateway when `AUTH_MODE=gateway`. Use `AUTH_MODE=no` only
for local development.

| Token role | Access |
| --- | --- |
| `workspace-api:admin` | All workspaces, workspace creation and deletion, environment choices, and token requests |
| `<workspace>:ws_admin` | Workspace management, credentials, and token requests |
| `<workspace>:ws_access` | Workspace details, sessions, and service and OAuth2 credentials |
| `<workspace>:ws_api` | Service credentials |

The API needs these Kubernetes permissions in the namespaces it manages:

| Resources | Verbs |
| --- | --- |
| Storage and Datalab resources | `get`, `list`, `create`, `patch`, `delete` |
| Referenced Secrets | `get` in each referenced namespace |

The API also needs cluster-scoped `get` and `list` access to
`environmentconfigs.apiextensions.crossplane.io` and
`compositions.apiextensions.crossplane.io` for workspace creation and environment
selection. Workspace roles such as `<workspace>:ws_admin` cannot create or
delete whole workspaces.

## Development

Use Python 3.12, `uv`, and `npm`. Run backend commands from the repo root.

```bash
uv sync --extra dev
uv run pre-commit install
KUBECONFIG=/path/to/config uv run uvicorn workspace_api:app --reload --port=8181
```

For UI development, run `npm ci`, then `npm run dev`, in
`workspace_ui/management`. Start the backend with `UI_MODE=ui` and
`FRONTEND_URL=http://localhost:9000`. Open
`http://localhost:8181/workspaces/<workspace-name>`.

For a sample UI without a backend, run `npm run shell+dev` in
`workspace_ui/management` and open `http://localhost:8181`. Changes need a
backend; the sample data is in `workspace_ui/luigi-shell/standalone/config/app-config.js`.

To serve built assets, run `workspace_ui/build_dist.sh`, then start the backend
with `UI_MODE=ui`. The build keeps the previous bundle until the new one is
ready. Rebuild after UI changes. Startup fails if the required UI files are
missing.

UI entry pages and files without a content hash revalidate on each request.
Assets with a content hash can stay cached for one year. Missing files are not
cached.

Run the backend checks from the repo root:

```bash
uv run pytest workspace_api/tests
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pre-commit run --all-files
git diff --check
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
| `DISABLE_STORAGE` | `false` | Disable Storage and hide its features. |
| `DISABLE_DATALAB` | `false` | Disable Datalab and hide its features. |
| `USE_VCLUSTER` | `false` | Add a virtual cluster named `vc0` to new workspaces. |
| `SESSION_MODE` | `on` | Initial default session: `on`, `auto`, or `off`. |
| `MAX_SESSIONS` | `3` | Limit on declared sessions per workspace. |
| `STORES` | `postgres,redis,mongo` | Enabled store names. Empty disables all stores. |
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
