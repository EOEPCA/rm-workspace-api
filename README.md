# Workspace API

Share S3 data, manage databases, open browser sessions, and give automated tasks
access to workspace services. Workspace API provides a web UI for your team
and an HTTP API for scripts and jobs.

## Open your workspace

Sign in to your Workspace API deployment and open `/workspaces` to choose a
workspace. Workspace API administrators can also create and delete workspaces on this
page.

- **Dashboard:** find service connections, copy credentials, and download
  kubeconfigs.
- **Management:** manage members, buckets, data services, sessions, and access
  profiles. These controls are available to workspace admins.
- **Links:** open ready sessions and browser services published by the provider,
  such as the Data browser.

See the [EOEPCA Workspace quickstart](https://eoepca.readthedocs.io/projects/workspace/en/latest/getting-started/quickstart/)
for a walkthrough with screenshots.

## Manage data services

Create a PostgreSQL, MongoDB, or Redis service in **Management → Stores** and
choose its storage size.

Find connection details and credentials on the dashboard, then use the service
from your application, browser session, or automated task.

## Give access to Kubernetes

In **Management → Vclusters**, select **Add access profile**. Give the profile
a name, choose a namespace, and select `view`, `edit`, or `admin`. The default
is `edit`. The profile grants that role within the selected namespace.

Use the dashboard to download a kubeconfig for a profile. Access profiles can
also limit the Kubernetes permissions available to an automated task.

## Run automated tasks

A workspace admin can request a token and pass it to a script or batch job.
The job uses that token to get the service credentials it needs.

Two token options are available:

| Your task needs | Token option |
| --- | --- |
| Workspace service credentials | A service-account token for the workspace. |
| Service credentials and selected Kubernetes access | A user-token exchange with the required access profiles. |

See [Automation and workspace tokens](docs/workspace-tokens.md) for commands,
request and response examples, and provider configuration. The running API's
`/docs` page contains the endpoint reference.

## Set up Workspace API

Install [Provider Storage](https://github.com/versioneer-tech/provider-storage)
for buckets and [Provider Datalab](https://github.com/versioneer-tech/provider-datalab)
for members, data services, sessions, and virtual clusters on the API's cluster.
Either provider can be used alone. The UI shows the available features.

For installation, authentication, and configuration, see [Setup](docs/setup.md).

## Development

Use the Python and uv versions in the [Dockerfile](Dockerfile), plus Docker and
rsync. Run from the repo root:

```bash
uv sync --locked --extra dev --extra prod
uv run --no-sync pre-commit install
workspace_ui/build_dist.sh
UI_MODE=ui KUBECONFIG=/path/to/config uv run --no-sync uvicorn workspace_api:app --reload --port 8181
```

Add `--no-cache` to the UI build command to rebuild without Docker's build cache.
Run checks with:

```bash
uv run --no-sync pre-commit run --all-files
docker build --pull --target api-test .
docker build --pull --target ui-test .
```

GitHub CI runs pytest and Node.js tests, ESLint, Ruff, mypy, markdownlint, Hadolint,
Gitleaks, Trivy vulnerability scans and SBOM generation, and pre-commit file checks
on PRs, pushes to `main`, release tags, and daily. Local Git hooks also use Commitizen.
Dependabot opens update PRs daily for Docker images and weekly for Python, npm,
and GitHub Actions.

## License

[Apache 2.0](LICENSE)
