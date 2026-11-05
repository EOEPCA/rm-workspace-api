# Workspace API

Share S3 data, manage databases, open browser sessions, and give automated tasks
access to workspace services. Workspace API provides a web UI for your team
and an HTTP API for scripts and jobs.

## What you can do

| Task | How Workspace API helps |
| --- | --- |
| Share data | Create buckets, request access to shared buckets, and retrieve S3 credentials. |
| Use data services | Create PostgreSQL, MongoDB, and Redis stores and get their connection details. |
| Work as a team | Add workspace members and assign user or admin roles. |
| Run browser sessions | Create, start, stop, and open sessions from your workspace. |
| Use Kubernetes | Create namespace access profiles and download kubeconfigs. |
| Automate work | Give a job a workspace token to retrieve service credentials or use selected Kubernetes permissions. |

## Open your workspace

Sign in to your Workspace API deployment and open `/workspaces` to choose a
workspace.

- **Dashboard:** find service connections, copy credentials, and download
  kubeconfigs.
- **Management:** manage members, buckets, data services, sessions, and access
  profiles. These controls are available to workspace admins.
- **Sessions:** open a session from workspace navigation, or use the Sessions
  management tab to create, start, stop, and remove sessions.

For example, create a bucket for a team's input data, give colleagues access,
and use a browser session to work with it. A batch job can use the same
workspace to read inputs and write results.

See the [EOEPCA Workspace quickstart](https://eoepca.readthedocs.io/projects/workspace/en/latest/getting-started/quickstart/)
for a walkthrough with screenshots.

## Provision managed services

Create a service in **Management → Stores** and choose the storage your
application needs. The platform operates the service and provides operational
guarantees, such as backups, through its configured service policies.

- **PostgreSQL:** store relational data and query it with SQL.
- **MongoDB:** store and query document data.
- **Redis:** cache data for applications and jobs.

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
The job uses that token to retrieve the service credentials it needs. For
example, it can get S3 credentials, read files from a bucket, and upload results.

Two token options are available:

| Your task needs | Token option |
| --- | --- |
| Workspace service credentials | A service-account token for the workspace. |
| Service credentials and selected Kubernetes access | A user-token exchange with the required access profiles. |

See [Automation and workspace tokens](docs/workspace-tokens.md) for commands,
request and response examples, and provider configuration. The running API's
`/docs` page contains the endpoint reference.

## Set up Workspace API

> [!NOTE]
> Requires [provider-datalab](https://github.com/versioneer-tech/provider-datalab) `>= 0.12.0`
> and [provider-storage](https://github.com/versioneer-tech/provider-storage) `>= 0.4.0`,
> installed on the same Kubernetes cluster.

Workspace API uses Provider Storage for buckets and Provider Datalab for
members, data services, sessions, and virtual clusters. The UI shows the
features enabled for your deployment.

For installation, authentication, configuration, and local development, see
[Setup and development](docs/setup.md).

## License

[Apache 2.0](LICENSE)
