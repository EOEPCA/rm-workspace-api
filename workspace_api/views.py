import base64
import enum
import logging
import uuid
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Union, cast

import kubernetes.client
import kubernetes.client.rest
from fastapi import BackgroundTasks, Header, HTTPException, Path, Request, Response
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from pydantic import BaseModel
from slugify import slugify

from workspace_api import app, config, templates

logger = logging.getLogger(__name__)

CONTAINER_REGISTRY_SECRET_NAME = "container-registry"


@app.on_event("startup")
async def load_k8s_config():
    try:
        k8s_config.load_kube_config()
    except Exception:
        try:
            k8s_config.load_incluster_config()
        except Exception:
            logger.error("Failed to load Kubernetes configuration", exc_info=True)
            raise


def fetch_secret(secret_name: str, namespace: str) -> Optional[k8s_client.V1Secret]:
    try:
        return cast(
            k8s_client.V1Secret,
            k8s_client.CoreV1Api().read_namespaced_secret(
                name=secret_name,
                namespace=namespace,
            ),
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        else:
            raise


class WorkspaceCreate(BaseModel):
    preferred_name: str = ""
    default_owner: str = ""


@app.post("/workspaces", status_code=HTTPStatus.CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    background_tasks: BackgroundTasks,
    authorization: Union[str, None] = Header(default=None),
):
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
    cluster_status: str
    members: List[str]
    buckets: List[str]


@app.put("/workspaces/{workspace_name}", status_code=HTTPStatus.ACCEPTED)
async def update_workspace(workspace_name: str, update: WorkspaceEdit):
    dynamic_client = DynamicClient(kubernetes.client.ApiClient())
    workspace_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
    try:
        workspace_api.get(name=workspace_name, namespace=current_namespace())
        patch_body = {
            "spec": {
                "vcluster": update.cluster_status,
                "members": update.members,
                "extraBuckets": update.buckets,
            }
        }
        workspace_api.patch(name=workspace_name, namespace=current_namespace(), body=patch_body)
        return {"name": workspace_name}
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
        else:
            raise


def workspace_name_from_preferred_name(preferred_name: str):
    safe_name = slugify(preferred_name, max_length=32)
    if not safe_name:
        safe_name = str(uuid.uuid4())
    return config.PREFIX_FOR_NAME + "-" + safe_name


class WorkspaceStatus(enum.Enum):
    provisioning = "provisioning"
    ready = "ready"
    unknown = "unknown"


class Storage(BaseModel):
    credentials: Dict[str, str]


class Cluster(BaseModel):
    config: str
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
    spec: Optional[Any] = None
    storage: Optional[Storage] = None
    container_registry: Optional[ContainerRegistryCredentials] = None
    cluster: Optional[Cluster] = None
    endpoints: List[Endpoint] = []
    members: List[Member] = []
    buckets: List[Bucket] = []


def get_workspace_internal(workspace_name: str):
    try:
        dynamic_client = DynamicClient(k8s_client.ApiClient())
        workspace_resource = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
        workspace = workspace_resource.get(name=workspace_name, namespace=current_namespace())
        ignored_keys = {
            "compositeDeletePolicy",
            "compositionRef",
            "compositionRevisionRef",
            "compositionUpdatePolicy",
            "resourceRef",
        }
        spec = {
            k: v for k, v in (workspace.spec.to_dict() if hasattr(workspace.spec, "to_dict") else workspace.spec).items() if k not in ignored_keys
        }

        if not spec:
            return Workspace(name=workspace_name, status=WorkspaceStatus.unknown, spec=None)
    except Exception:
        return Workspace(name=workspace_name, status=WorkspaceStatus.unknown, spec=None)

    try:
        workspace_secret = cast(
            k8s_client.V1Secret,
            k8s_client.CoreV1Api().read_namespaced_secret(
                name=config.WORKSPACE_SECRET_NAME,
                namespace=workspace_name,
            ),
        )
    except Exception as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return Workspace(name=workspace_name, status=WorkspaceStatus.provisioning, spec=spec)
        else:
            logger.warning(f"Failed to load workspace secret: {e}")
            return Workspace(name=workspace_name, status=WorkspaceStatus.unknown, spec=None)

    envs = {k: base64.b64decode(v).decode() for k, v in workspace_secret.data.items()}
    credentials = {
        "bucketname": workspace_name,
        "access": envs.get("AWS_ACCESS_KEY_ID", envs.get("access", "")),
        "secret": envs.get("AWS_SECRET_ACCESS_KEY", envs.get("secret", "")),
        "endpoint": envs.get("AWS_ENDPOINT_URL", envs.get("endpoint", "")),
        "region": envs.get("AWS_REGION", envs.get("region", "")),
    }

    container_registry = None
    try:
        container_registry_secret = cast(
            k8s_client.V1Secret,
            k8s_client.CoreV1Api().read_namespaced_secret(
                name=CONTAINER_REGISTRY_SECRET_NAME,
                namespace=workspace_name,
            ),
        )
        container_registry = ContainerRegistryCredentials(
            username=base64.b64decode(container_registry_secret.data["username"]).decode(),
            password=base64.b64decode(container_registry_secret.data["password"]).decode(),
        )
    except Exception as e:
        logger.warning(f"Failed to load container registry secret: {e}")

    endpoints = []
    try:
        ingress_endpoints = [
            Endpoint(
                id=ingress.metadata.name,
                url=ingress.spec.rules[0].host if ingress.spec.rules else "",
            )
            for ingress in cast(
                List[k8s_client.V1Ingress],
                k8s_client.NetworkingV1Api().list_namespaced_ingress(namespace=workspace_name).items,
            )
        ]
        endpoints.extend(ingress_endpoints)
    except Exception as e:
        logger.warning(f"Failed to load ingresses: {e}")

    try:
        apisix_routes = k8s_client.CustomObjectsApi().list_namespaced_custom_object(
            group="apisix.apache.org",
            version="v2",
            namespace=workspace_name,
            plural="apisixroutes",
        )
        apisix_endpoints = [
            Endpoint(
                id=route["metadata"]["name"],
                url=",".join(list(set(match for http in route.get("spec", {}).get("http", []) for match in http.get("match", {}).get("hosts", [])))),
            )
            for route in cast(List[dict], apisix_routes["items"])
        ]
        endpoints.extend(apisix_endpoints)
    except Exception as e:
        logger.warning(f"Failed to load APISIX routes: {e}")

    try:
        memberships = k8s_client.CustomObjectsApi().list_cluster_custom_object(
            group="group.keycloak.crossplane.io",
            version="v1alpha1",
            plural="memberships",
        )["items"]

        members = [
            Member(name=username)
            for m in memberships
            if m.get("spec", {}).get("forProvider", {}).get("groupIdRef", {}).get("name") == workspace_name
            for username in m.get("spec", {}).get("forProvider", {}).get("members", [])
        ]
    except Exception as e:
        logger.warning(f"Failed to load Keycloak memberships: {e}")
        members = []

    try:
        policies = cast(
            List[dict],
            k8s_client.CustomObjectsApi().list_cluster_custom_object(group="minio.crossplane.io", version="v1", plural="policies")["items"],
        )
        buckets = []
        for policy in policies:
            parts = policy.get("metadata", {}).get("name", "").split(".")
            if len(parts) == 3 and parts[0] == workspace_name:
                buckets.append(Bucket(name=parts[2], policy=parts[1]))
    except Exception as e:
        logger.warning(f"Failed to load MinIO policies: {e}")
        buckets = []

    return Workspace(
        name=workspace_name,
        status=WorkspaceStatus.ready,
        spec=spec,
        storage=Storage(credentials=credentials),
        container_registry=container_registry,
        cluster=Cluster(
            config=envs.get("KUBECONFIG"),
            status="active" if any(e.id == "vcluster" for e in endpoints) else "suspended",
        ),
        endpoints=endpoints,
        members=members,
        buckets=buckets,
    )


@app.get("/workspaces/{workspace_name}", status_code=HTTPStatus.OK)
async def get_workspace(request: Request, workspace_name: str = Path(...)):
    workspace = get_workspace_internal(workspace_name)

    accept_header = request.headers.get("accept", "")
    if config.UI_MODE == "ui" or (request.query_params.get("devmode") == "true" and "text/html") in accept_header:
        workspace_data = base64.b64encode(workspace.model_dump_json().encode("utf-8")).decode("utf-8")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "base_path": request.url.path,
                "workspace_data": workspace_data,
            },
        )
    else:
        return workspace


workspace_path_type = Path(..., pattern=f"^{config.PREFIX_FOR_NAME}")


@app.delete("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
async def delete_workspace(workspace_name: str = workspace_path_type):
    try:
        dynamic_client = DynamicClient(kubernetes.client.ApiClient())
        workspace_api = dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace")
        workspace_api.delete(name=workspace_name, namespace=current_namespace())
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
        else:
            raise
    return Response(status_code=HTTPStatus.NO_CONTENT)


def current_namespace() -> str:
    try:
        return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read().strip()
    except FileNotFoundError:
        return "workspace"
