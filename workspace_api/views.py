# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import binascii
import enum
import logging
import re
import uuid
from http import HTTPStatus
from typing import Any

import kubernetes.client
import kubernetes.client.rest
from fastapi import HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from pydantic import BaseModel, Field
from slugify import slugify

from workspace_api import app, config, templates

logger = logging.getLogger(__name__)

# Validate workspace names to start with "<PREFIX_FOR_NAME>-", e.g., "ws-..."
WORKSPACE_NAME_PATTERN = rf"^{re.escape(config.PREFIX_FOR_NAME)}-"
workspace_path_type = Path(..., pattern=WORKSPACE_NAME_PATTERN)


@app.on_event("startup")
async def load_k8s_config() -> None:
    try:
        k8s_config.load_kube_config()
    except k8s_config.ConfigException:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            logger.exception("Failed to load Kubernetes configuration")
            raise


def fetch_secret(secret_name: str, namespace: str) -> k8s_client.V1Secret | None:
    """Fetch a secret from a namespace, returning None if not found."""
    try:
        return k8s_client.CoreV1Api().read_namespaced_secret(
            name=secret_name,
            namespace=namespace,
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        raise


class WorkspaceCreate(BaseModel):
    preferred_name: str = ""
    default_owner: str = ""


@app.post("/workspaces", status_code=HTTPStatus.CREATED)
async def create_workspace(data: WorkspaceCreate) -> dict[str, str]:
    workspace_name = workspace_name_from_preferred_name(data.preferred_name)

    dynamic_client = DynamicClient(kubernetes.client.ApiClient())
    workspace_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
    try:
        workspace_api.get(name=workspace_name, namespace=current_namespace())
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "Workspace with this name already exists"},
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            raise

    logger.info(f"Creating {workspace_name} in {current_namespace()}")

    workspace_api.create(
        {
            "apiVersion": "epca.eo/v1beta1",
            "kind": "Workspace",
            "metadata": {"name": workspace_name},
            "spec": {"owner": data.default_owner, "defaultBucket": workspace_name},
        },
        namespace=current_namespace(),
    )

    return {"name": workspace_name}


class WorkspaceEdit(BaseModel):
    name: str
    cluster_status: str = Field(..., alias="clusterStatus")
    members: list[str]
    extra_buckets: list[str] = Field(..., alias="extraBuckets")


@app.put("/workspaces/{workspace_name}", status_code=HTTPStatus.ACCEPTED)
async def update_workspace(workspace_name: str, update: WorkspaceEdit) -> dict[str, str]:
    logger.debug(f"Update {workspace_name} with {update}")

    dynamic_client = DynamicClient(kubernetes.client.ApiClient())
    workspace_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
    try:
        workspace_api.get(name=workspace_name, namespace=current_namespace())
        patch_body = {
            "spec": {
                "vcluster": update.cluster_status,
                "members": update.members,
                "extraBuckets": update.extra_buckets,
            }
        }
        workspace_api.patch(
            name=workspace_name,
            namespace=current_namespace(),
            body=patch_body,
            content_type="application/merge-patch+json",
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise
    else:
        return {"name": workspace_name}


def workspace_name_from_preferred_name(preferred_name: str) -> str:
    safe_name = slugify(preferred_name, max_length=32)
    if not safe_name:
        safe_name = str(uuid.uuid4())
    return config.PREFIX_FOR_NAME + "-" + safe_name


class WorkspaceStatus(str, enum.Enum):
    provisioning = "provisioning"
    ready = "ready"
    unknown = "unknown"


class Storage(BaseModel):
    credentials: dict[str, str]


class Cluster(BaseModel):
    config: str | None = None
    status: str


class Endpoint(BaseModel):
    id: str
    url: str


class ContainerRegistryCredentials(BaseModel):
    username: str
    password: str

    def base64_encode_as_single_string(self) -> str:
        return base64.b64encode(f"{self.username}:{self.password}".encode()).decode()


class Member(BaseModel):
    name: str


class Bucket(BaseModel):
    name: str
    policy: str


class Workspace(BaseModel):
    name: str
    status: WorkspaceStatus
    spec: Any | None = None
    storage: Storage | None = None
    container_registry: ContainerRegistryCredentials | None = None
    cluster: Cluster | None = None
    endpoints: list[Endpoint] = Field(default_factory=list)
    members: list[Member] = Field(default_factory=list)
    buckets: list[Bucket] = Field(default_factory=list)


def _get_workspace_resource(workspace_name: str, dynamic_client: DynamicClient) -> Any | None:
    """Fetch the workspace custom resource."""
    try:
        workspace_resource_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
        return workspace_resource_api.get(name=workspace_name, namespace=current_namespace())
    except kubernetes.client.rest.ApiException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            logger.error(f"Error fetching workspace CR for '{workspace_name}': {e}")
        return None


def _get_workspace_spec(workspace_cr: Any) -> dict[str, Any] | None:
    """Extract and clean the spec from the workspace custom resource."""
    if not hasattr(workspace_cr, "spec"):
        return None

    spec_dict = workspace_cr.spec.to_dict() if hasattr(workspace_cr.spec, "to_dict") else workspace_cr.spec

    ignored_keys = {
        "compositeDeletePolicy",
        "compositionRef",
        "compositionRevisionRef",
        "compositionUpdatePolicy",
        "resourceRef",
    }
    return {k: v for k, v in spec_dict.items() if k not in ignored_keys}


def _get_storage_and_envs(workspace_name: str) -> tuple[Storage, dict[str, str]] | None:
    """Fetch workspace secret and construct Storage object and envs dict."""
    workspace_secret = fetch_secret(config.WORKSPACE_SECRET_NAME, workspace_name)
    if not workspace_secret or not workspace_secret.data:
        return None

    try:
        envs = {k: base64.b64decode(v).decode("utf-8") for k, v in workspace_secret.data.items()}
        credentials = {
            "bucketname": workspace_name,
            "access": envs.get("AWS_ACCESS_KEY_ID", envs.get("access", "")),
            "secret": envs.get("AWS_SECRET_ACCESS_KEY", envs.get("secret", "")),
            "endpoint": envs.get("AWS_ENDPOINT_URL", envs.get("endpoint", "")),
            "region": envs.get("AWS_REGION", envs.get("region", "")),
        }
        return Storage(credentials=credentials), envs
    except (KeyError, TypeError, binascii.Error) as e:
        logger.warning(f"Error processing workspace secret for '{workspace_name}': {e}")
        return None


def _get_container_registry_credentials(workspace_name: str) -> ContainerRegistryCredentials | None:
    """Fetch container registry credentials."""
    secret = fetch_secret(config.CONTAINER_REGISTRY_SECRET_NAME, workspace_name)
    if not secret or not secret.data:
        return None

    try:
        username = base64.b64decode(secret.data["username"]).decode()
        password = base64.b64decode(secret.data["password"]).decode()
        return ContainerRegistryCredentials(username=username, password=password)
    except (KeyError, binascii.Error) as e:
        logger.warning(f"Failed to decode container registry secret for '{workspace_name}': {e}")
        return None


def _get_endpoints(workspace_name: str) -> list[Endpoint]:
    """Fetch endpoints from Ingresses and ApisixRoutes."""
    endpoints: list[Endpoint] = []
    try:
        ingresses = k8s_client.NetworkingV1Api().list_namespaced_ingress(namespace=workspace_name)
        endpoints.extend(
            Endpoint(id=ingress.metadata.name, url=ingress.spec.rules[0].host)
            for ingress in ingresses.items
            if ingress.metadata and ingress.spec and ingress.spec.rules
        )
    except kubernetes.client.rest.ApiException as e:
        logger.warning(f"Failed to load ingresses for '{workspace_name}': {e}")

    try:
        api = k8s_client.CustomObjectsApi()
        apisix_routes = api.list_namespaced_custom_object("apisix.apache.org", "v2", workspace_name, "apisixroutes")
        for route in apisix_routes.get("items", []):
            hosts = {
                match
                for http in route.get("spec", {}).get("http", [])
                for match in http.get("match", {}).get("hosts", [])
            }
            if hosts:
                endpoints.append(
                    Endpoint(
                        id=route.get("metadata", {}).get("name"),
                        url=",".join(sorted(hosts)),
                    )
                )
    except kubernetes.client.rest.ApiException as e:
        logger.warning(f"Failed to load APISIX routes for '{workspace_name}': {e}")
    return endpoints


def _get_members(workspace_name: str) -> list[Member]:
    """Fetch workspace members from Keycloak."""
    try:
        api = k8s_client.CustomObjectsApi()
        memberships = api.list_cluster_custom_object("group.keycloak.crossplane.io", "v1alpha1", "memberships")["items"]
        return [
            Member(name=username)
            for m in memberships
            if m.get("spec", {}).get("forProvider", {}).get("groupIdRef", {}).get("name") == workspace_name
            for username in m.get("spec", {}).get("forProvider", {}).get("members", [])
        ]
    except kubernetes.client.rest.ApiException as e:
        logger.warning(f"Failed to load Keycloak memberships for '{workspace_name}': {e}")
        return []


def _get_buckets(workspace_name: str) -> list[Bucket]:
    """Fetch bucket policies from MinIO."""
    try:
        api = k8s_client.CustomObjectsApi()
        policies = api.list_cluster_custom_object("minio.crossplane.io", "v1", "policies")["items"]
        return [
            Bucket(name=parts[2], policy=parts[1])
            for policy in policies
            if (parts := policy.get("metadata", {}).get("name", "").split("."))
            and len(parts) == 3
            and parts[0] == workspace_name
        ]
    except kubernetes.client.rest.ApiException as e:
        logger.warning(f"Failed to load MinIO policies for '{workspace_name}': {e}")
        return []


def get_workspace_internal(workspace_name: str) -> Workspace:
    """Assemble the full workspace details by querying multiple k8s resources."""
    dynamic_client = DynamicClient(k8s_client.ApiClient())
    workspace_cr = _get_workspace_resource(workspace_name, dynamic_client)
    if not workspace_cr:
        return Workspace(name=workspace_name, status=WorkspaceStatus.unknown)

    spec = _get_workspace_spec(workspace_cr)
    storage_and_envs = _get_storage_and_envs(workspace_name)

    if not storage_and_envs:
        return Workspace(name=workspace_name, status=WorkspaceStatus.provisioning, spec=spec)

    storage, envs = storage_and_envs
    container_registry = _get_container_registry_credentials(workspace_name)
    endpoints = _get_endpoints(workspace_name)
    members = _get_members(workspace_name)
    buckets = _get_buckets(workspace_name)

    cluster_status = "active" if any(e.id == "vcluster" for e in endpoints) else "suspended"
    cluster = Cluster(config=envs.get("KUBECONFIG"), status=cluster_status)

    return Workspace(
        name=workspace_name,
        status=WorkspaceStatus.ready,
        spec=spec,
        storage=storage,
        container_registry=container_registry,
        cluster=cluster,
        endpoints=endpoints,
        members=members,
        buckets=buckets,
    )


@app.get(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.OK,
    response_model=Workspace,
)
async def get_workspace(request: Request, workspace_name: str = workspace_path_type) -> Response:
    logger.warning("GET workspace %s", workspace_name)
    workspace = get_workspace_internal(workspace_name)

    accept_header = request.headers.get("accept", "")
    if (
        "text/html" in accept_header
        and templates is not None
        and (config.UI_MODE == "ui" or request.query_params.get("devmode") == "true")
    ):
        workspace_data = base64.b64encode(workspace.model_dump_json().encode("utf-8")).decode("utf-8")
        return templates.TemplateResponse(
            "ui.html",
            {
                "request": request,
                "base_path": request.url.path,
                "workspace_data": workspace_data,
                "frontend_url": config.FRONTEND_URL,
            },
        )
    return JSONResponse(workspace.model_dump(), status_code=HTTPStatus.OK)


@app.delete("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
async def delete_workspace(workspace_name: str = workspace_path_type) -> Response:
    try:
        dynamic_client = DynamicClient(kubernetes.client.ApiClient())
        workspace_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
        workspace_api.delete(name=workspace_name, namespace=current_namespace())
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise
    return Response(status_code=HTTPStatus.NO_CONTENT)


def current_namespace() -> str:
    """Get the current Kubernetes namespace."""
    try:
        return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read().strip()
    except FileNotFoundError:
        return "workspace"
