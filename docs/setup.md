# Setup

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
docker buildx build --pull --no-cache-filter runtime-base --load -t workspace-api .
```

Run it with a mounted kubeconfig or a Kubernetes ServiceAccount. Set
`UI_MODE=ui` to serve the UI, and expose port 8181.

Pass the release tag with `--build-arg VERSION=<tag>` to set the installed Python
package version and image label. Without this argument, the version is
`0.0.0+local`. CI uses the release tag, or a development version with the commit
ID for other builds.

Dependency installation has separate cache layers from application source.
CI uses these layers and reruns the test stages. It also bypasses the
`runtime-base` cache so OS package updates run for each candidate image.

### Container security checks

The runtime uses a slim base image. Build tools stay in the builder stages.
Python packages come from `uv.lock`; frontend packages come from
`workspace_ui/management/package-lock.json`. Keep these files in each dependency
update. The build fails if the Python lockfile does not match `pyproject.toml`.

Dependabot opens update PRs for base images, Python and frontend packages, and
GitHub Actions. Base images use a version and digest. Review and merge digest
updates to receive new base image packages. Keep the Python builder and runtime
on the same Python version and Debian release.

The **Container security** workflow runs tests, builds the image, and scans the
image and frontend production dependencies. It blocks all critical findings,
high findings with an available fix, and an unsupported runtime OS. Frontend
build tool findings are reported separately and do not block publication.
Other findings stay in the JSON reports. Each run keeps scan reports and
CycloneDX package inventories as workflow artifacts. Make `tests` and
`build-and-scan` required PR checks in the repository rules.

Release tags publish the same image that passed the checks. A daily run also
scans the image and shipped frontend inventory for the latest stable release
tag. To check another deployed image, run the workflow manually with its GHCR
tag or digest in `image_ref`.
Check failed scheduled runs and review findings that have no fix. An image
update needs a new release and deployment; a scan does not update running pods.
