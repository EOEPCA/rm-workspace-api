import base64
import enum
from http import HTTPStatus
import uuid
from typing import cast, Optional, List, Dict, Any, Union
import string
import secrets
import logging
from fastapi import HTTPException, Path, Response, BackgroundTasks, Header, Request

# from kubernetes.client.models.v1_secret import V1Secret
import kubernetes.client.rest
import kubernetes.watch
import kubernetes.client
from kubernetes import config as k8s_config, client as k8s_client
from kubernetes.client.models import V1ObjectMeta
from kubernetes.dynamic import DynamicClient
import requests
import requests.exceptions
from slugify import slugify
from pydantic import BaseModel


from workspace_api import app, config

logger = logging.getLogger(__name__)

CONTAINER_REGISTRY_SECRET_NAME = "container-registry"


@app.on_event("startup")
async def load_k8s_config():
    try:
        k8s_config.load_kube_config()
    except Exception:
        k8s_config.load_incluster_config()


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
    try:
        dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace").get(name=workspace_name)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "Workspace with this name already exists"},
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            pass
        else:
            raise

    print("all good")

    workspace_data = {
        "apiVersion": "epca.eo/v1beta1",
        "kind": "Workspace",
        "metadata": V1ObjectMeta(name=workspace_name),
        "spec" : {
            "subscription": "silver",
            "owner": data.default_owner
        }
    }
    print(f"creating {workspace_name} in {current_namespace()}")
    dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace").create(workspace_data, namespace=current_namespace())

    return {"name": workspace_name}


def create_harbor_user(workspace_name: str) -> None:
    """Create user in harbor via api and store credentials in secret"""
    logger.info(f"Creating container registry user {workspace_name}")
    alphabet = string.ascii_letters + string.digits
    harbor_user_password = "".join(secrets.choice(alphabet) for i in range(30))

    k8s_client.CoreV1Api().create_namespaced_secret(
        namespace=workspace_name,
        body=k8s_client.V1Secret(
            metadata=k8s_client.V1ObjectMeta(
                name=CONTAINER_REGISTRY_SECRET_NAME,
            ),
            data={
                "username": base64.b64encode(workspace_name.encode()).decode(),
                "password": base64.b64encode(harbor_user_password.encode()).decode(),
            },
        ),
    )

    response = requests.post(
        f"{config.HARBOR_URL}/api/v2.0/users",
        json={
            "username": workspace_name,
            "password": harbor_user_password,
            "email": f"{workspace_name}@example.com",
            "realname": workspace_name,
            "comment": "Auto-created by workspace api",
        },
        auth=(config.HARBOR_ADMIN_USERNAME, config.HARBOR_ADMIN_PASSWORD),
    )
    response.raise_for_status()


def workspace_name_from_preferred_name(preferred_name: str):
    safe_name = slugify(preferred_name, max_length=32)
    if not safe_name:
        safe_name = str(uuid.uuid4())

    return config.PREFIX_FOR_NAME + "-" + safe_name


class WorkspaceStatus(enum.Enum):
    ready = "ready"
    provisioning = "provisioning"


class Endpoint(BaseModel):
    id: str
    url: str


class Storage(BaseModel):
    credentials: Dict[str, str]


class Runtime(BaseModel):
    envs: Dict[str, str]


class ContainerRegistryCredentials(BaseModel):
    username: str
    password: str

    def base64_encode_as_single_string(self) -> str:
        return base64.b64encode(f"{self.username}:{self.password}".encode()).decode()


class Workspace(BaseModel):
    status: WorkspaceStatus

    # NOTE: these are defined iff the workspace is ready
    endpoints: List[Endpoint] = []
    storage: Optional[Storage]
    runtime: Optional[Runtime]

    container_registry: Optional[ContainerRegistryCredentials]


# only allow workspaces starting with the prefix for actions
workspace_path_type = Path(..., regex=f"^{config.PREFIX_FOR_NAME}")


@app.get("/debug", include_in_schema=False)
async def get_debug(request: Request):
    return {"headers": request.headers}


@app.get("/workspaces/{workspace_name}", response_model=Workspace)
async def get_workspace(workspace_name: str = workspace_path_type):
    secret = fetch_secret(
        secret_name=config.WORKSPACE_SECRET_NAME,
        namespace=workspace_name,
    )
    # compatibility v1
    if not secret:
        secret = fetch_secret(
            secret_name="bucket",
            namespace=workspace_name,
        )
    if secret:
        return serialize_workspace(workspace_name, secret=secret)
    else:
        return Workspace(
            status=WorkspaceStatus.provisioning, storage=None, runtime=None, container_registry=None
        )


def serialize_workspace(workspace_name: str, secret: k8s_client.V1Secret) -> Workspace:
    ingress_endpoints = [
        Endpoint(
            id=ingress.metadata.name,
            url=ingress.spec.rules[0].host if ingress.spec.rules else ""
        )
        for ingress in cast(
            List[k8s_client.V1Ingress],
            k8s_client.NetworkingV1Api()
            .list_namespaced_ingress(namespace=workspace_name)
            .items,
        )
    ]

    apisix_route_endpoints = [
        Endpoint(
            id=apisix_route["metadata"]["name"],
            url=",".join(
                list(set(
                    match
                    for http in apisix_route.get("spec", {}).get("http", [])
                    for match in http.get("match", {}).get("hosts", [])
                ))
            )
        )
        for apisix_route in cast(
            List[dict],
            k8s_client.CustomObjectsApi()
            .list_namespaced_custom_object(
                group="apisix.apache.org",
                version="v2",
                namespace=workspace_name,
                plural="apisixroutes",
            )["items"],
        )
    ]

    endpoints = ingress_endpoints + apisix_route_endpoints

    envs: Dict[str, Any] = {
        k: base64.b64decode(v) for k, v in secret.data.items()
    }

    # compatibility v1
    credentials: Dict[str, Any] = {
        "bucketname": workspace_name,
        "access": envs.get("AWS_ACCESS_KEY_ID", envs.get("access", "")),
        "secret": envs.get("AWS_SECRET_ACCESS_KEY", envs.get("secret", "")),
        "endpoint": envs.get("AWS_ENDPOINT_URL", envs.get("endpoint", "")),
        "region": envs.get("AWS_REGION", envs.get("region", ""))
    }

    return Workspace(
        status=WorkspaceStatus.ready,  # only ready workspaces can be serialized
        endpoints=endpoints,
        storage=Storage(credentials=credentials),
        runtime=Runtime(envs=envs),
        container_registry=fetch_container_registry_credentials(workspace_name),
    )


@app.delete("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
async def delete_workspace(workspace_name: str = workspace_path_type):
    try:
        dynamic_client = DynamicClient(kubernetes.client.ApiClient())
        dynamic_client.resources.get(api_version="epca.eo/v1beta1", kind="Workspace").delete(name=workspace_name, namespace=current_namespace())
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
        else:
            raise

    return Response(status_code=HTTPStatus.NO_CONTENT)


def fetch_container_registry_credentials(
    workspace_name: str,
) -> ContainerRegistryCredentials | None:
    logger.info("Fetching container registry secret")
    container_registry_secret = fetch_secret(
        CONTAINER_REGISTRY_SECRET_NAME, namespace=workspace_name
    )
    return (
        ContainerRegistryCredentials(
            username=base64.b64decode(
                container_registry_secret.data["username"]
            ).decode(),
            password=base64.b64decode(
                container_registry_secret.data["password"]
            ).decode(),
        )
        if container_registry_secret
        else None
    )


def current_namespace() -> str:
    try:
        return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()
    except FileNotFoundError:
        return "workspace"
