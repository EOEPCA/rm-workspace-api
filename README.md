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

For installation, authentication, configuration, and local development, see
[Setup and development](docs/setup.md).

## License

[Apache 2.0](LICENSE)
