import base64
import enum
from http import HTTPStatus
import uuid
from typing import cast, Optional, List, Dict, Any
import asyncio
from urllib.parse import urlparse
import string
import secrets
import logging
import json

import jinja2
import yaml
from fastapi import HTTPException, Path, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from kubernetes.client.models.v1_secret import V1Secret
import kubernetes.client.rest
import kubernetes.watch
from kubernetes import config as k8s_config, client as k8s_client
import requests
import requests.exceptions
from slugify import slugify
from pydantic import BaseModel
import aioredis

from workspace_api import app, config


# TODO: fix logging output with gunicorn
logger = logging.getLogger(__name__)

CONTAINER_REGISTRY_SECRET_NAME = "container-registry"


@app.on_event("startup")
async def load_k8s_config():
    try:
        k8s_config.load_kube_config()
    except Exception:
        # load_kube_config might throw anything :/
        k8s_config.load_incluster_config()


def namespace_exists(workspace_name) -> bool:
    try:
        k8s_client.CoreV1Api().read_namespace(name=workspace_name)
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return False
        else:
            raise
    else:
        return True


def fetch_secret(
    secret_name: str, namespace: str
) -> Optional[k8s_client.V1Secret]:
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
    data: WorkspaceCreate, background_tasks: BackgroundTasks
):

    workspace_name = workspace_name_from_preferred_name(data.preferred_name)
    bucket_endpoint_url = config.BUCKET_ENDPOINT_URL

    if namespace_exists(workspace_name):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "Namespace already exists"},
        )

    k8s_client.CoreV1Api().create_namespace(
        k8s_client.V1Namespace(
            metadata=k8s_client.V1ObjectMeta(
                name=workspace_name,
            )
        )
    )

    # create_bucket(workspace_name=workspace_name)
    # TODO: specify post body
    response = requests.post(bucket_endpoint_url, data={})
    if response.status == 200:
        # we have a bucket created, we create the secret and continue setting up workspace
        create_bucket_secret(workspace_name=workspace_name, credentials=response.body)

    elif response.status == 201:
        # async approach
        # wait for the secret to be created
        # TODO determine the timeout & time interval values from config ?
        background_tasks.add_task(wait_for_secret, response.body, 100, 10)

    # TODO: create the workspace using the secret

    create_uma_client_credentials_secret(workspace_name=workspace_name)

    create_harbor_user(workspace_name=workspace_name)

    background_tasks.add_task(
        install_workspace_phase2,
        workspace_name=workspace_name,
        default_owner=data.default_owner,
    )

    return {"name": workspace_name}


def create_bucket_secret(workspace_name: str, credentials: Dict[str, Any]) -> None:

    logger.info(f"Creating secret for namespace {workspace_name}")
    k8s_client.CoreV1Api().create_namespaced_secret(
        namespace=workspace_name,
        body=k8s_client.V1Secret(
            metadata=k8s_client.V1ObjectMeta(
                name=CONTAINER_REGISTRY_SECRET_NAME,
            ),
            data={
                "username": base64.b64encode(credentials["workspace_name"].encode()).decode(),
                "password": base64.b64encode(
                    credentials["password"].encode()
                ).decode(),
            },
        )
    )


async def wait_for_secret(
        workspace_name: str, res: object , time_out: int, time_interval: int) -> V1Secret:

    timer = 0
    while res.status == 201:
        await asyncio.sleep(time_interval)
        timer += time_interval
        if timer > time_out:
            # TODO: raise a timeout exception
            break
        if res.status == 200:
            return create_bucket_secret(workspace_name=workspace_name, credentials=res.body)


def create_bucket(workspace_name: str) -> None:
    logger.info(f"Creating bucket in namespace {workspace_name}")
    group = "epca.eo"
    version = "v1alpha1"
    k8s_client.CustomObjectsApi().create_namespaced_custom_object(
        group=group,
        version=version,
        plural="buckets",
        namespace=config.NAMESPACE_FOR_BUCKET_RESOURCE,
        body={
            "apiVersion": f"{group}/{version}",
            "kind": "Bucket",
            "metadata": {
                # TODO: better name for bucket resource?
                "name": workspace_name,
                "namespace": config.NAMESPACE_FOR_BUCKET_RESOURCE,
            },
            "spec": {
                # we use the workspace name as bucket name since it's a good unique name
                "bucketName": workspace_name,
                "secretName": config.WORKSPACE_SECRET_NAME,
                "secretNamespace": workspace_name,
            },
        },
    )


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
                "password": base64.b64encode(
                    harbor_user_password.encode()
                ).decode(),
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


def create_uma_client_credentials_secret(workspace_name: str):
    logger.info("Creating uma client credentials secret")
    original_secret = k8s_client.CoreV1Api().read_namespaced_secret(
        name=config.UMA_CLIENT_SECRET_NAME,
        namespace=config.UMA_CLIENT_SECRET_NAMESPACE,
    )
    k8s_client.CoreV1Api().create_namespaced_secret(
        namespace=workspace_name,
        body=k8s_client.V1Secret(
            metadata=k8s_client.V1ObjectMeta(
                name=config.UMA_CLIENT_SECRET_NAME,
            ),
            data=original_secret.data,
        ),
    )


def wait_for_namespace_secret(workspace_name) -> V1Secret:
    watch = kubernetes.watch.Watch()
    for event in watch.stream(
        k8s_client.CoreV1Api().list_namespaced_secret,
        namespace=workspace_name,
    ):
        event_type = event["type"]
        event_secret: k8s_client.V1Secret = event["object"]
        event_secret_name = event_secret.metadata.name
        logger.info(f"Received secret event {event_type} {event_secret_name}")

        if (
            event_type == "ADDED"
            and event_secret_name == config.WORKSPACE_SECRET_NAME
        ):
            logger.info("Found the secret we were looking for")
            watch.stop()
            return event_secret

    raise Exception("Watch aborted")


def install_workspace_phase2(
    workspace_name, default_owner=None, patch=False
) -> None:
    """Wait for secret, then install helm chart"""
    secret = wait_for_namespace_secret(workspace_name=workspace_name)

    logger.info(f"Install phase 2 for {workspace_name}")

    found_hr = False
    if patch:
        response = k8s_client.CustomObjectsApi().list_namespaced_custom_object(
            group="helm.toolkit.fluxcd.io",
            plural="helmreleases",
            version="v2beta1",
            namespace=workspace_name,
        )
        for item in response["items"]:
            try:
                if item["spec"]["chart"]["spec"]["chart"] == "resource-guard":
                    found_hr = True
                    default_owner = item["spec"]["values"]["global"]["default_owner"]
                    break

            except KeyError:
                pass

    try:
        deploy_helm_releases(
            workspace_name=workspace_name,
            is_update=found_hr,
            secret=secret,
            default_owner=default_owner,
        )
    except Exception as e:
        logger.critical(e, exc_info=True)


def deploy_helm_releases(
    workspace_name: str,
    is_update: bool,
    secret: k8s_client.V1Secret,
    default_owner: str,
):

    hrs = (
        k8s_client.CoreV1Api()
        .read_namespaced_config_map(
            name=config.WORKSPACE_CHARTS_CONFIG_MAP,
            namespace=current_namespace(),
        )
        .data
    )
    logger.info(f"Deploying {len(hrs)} HelmReleases: {list(hrs)}")
    for hr_key, hr_raw_content in hrs.items():
        logger.info(f"Deploying HelmRelease {hr_key}")

        hr_rendered = (
            jinja2.Environment()
            .from_string(
                hr_raw_content,
            )
            .render(
                workspace_name=workspace_name,
                access_key_id=base64.b64decode(secret.data["access"]).decode(),
                secret_access_key=base64.b64decode(
                    secret.data["secret"]
                ).decode(),
                bucket=base64.b64decode(secret.data["bucketname"]).decode(),
                projectid=base64.b64decode(secret.data["projectid"]).decode(),
                default_owner=default_owner,
            )
        )

        # we have to implement kubectl apply here because kubernetes-python can only create using utils.create_from_yaml
        # https://github.com/kubernetes-client/python/issues/1737
        hr_rendered_parsed = yaml.safe_load(hr_rendered)

        group, version = hr_rendered_parsed["apiVersion"].split("/")
        plural = hr_rendered_parsed["kind"].lower() + "s"

        if is_update:
            k8s_client.CustomObjectsApi().patch_namespaced_custom_object(
                name=hr_rendered_parsed["metadata"]["name"],
                group=group,
                plural=plural,
                version=version,
                namespace=workspace_name,
                body=hr_rendered_parsed,
            )
        else:
            k8s_client.CustomObjectsApi().create_namespaced_custom_object(
                group=group,
                plural=plural,
                version=version,
                namespace=workspace_name,
                body=hr_rendered_parsed,
            )

    logger.info("All HelmReleases have been deployed")


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
    # url: str
    credentials: Dict[str, str]
    # quota_in_mb: int


class ContainerRegistryCredentials(BaseModel):
    username: str
    password: str


class Workspace(BaseModel):
    status: WorkspaceStatus

    # NOTE: these are defined iff the workspace is ready
    endpoints: List[Endpoint] = []
    storage: Optional[Storage]

    container_registry: Optional[ContainerRegistryCredentials]


# only allow workspaces starting with the prefix for actions
workspace_path_type = Path(..., regex=f"^{config.PREFIX_FOR_NAME}")


@app.get("/workspaces/{workspace_name}", response_model=Workspace)
async def get_workspace(workspace_name: str = workspace_path_type):

    if not namespace_exists(workspace_name):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    secret = fetch_secret(
        secret_name=config.WORKSPACE_SECRET_NAME,
        namespace=workspace_name,
    )
    if secret:
        return serialize_workspace(workspace_name, secret=secret)
    else:
        return Workspace(status=WorkspaceStatus.provisioning)


def serialize_workspace(
    workspace_name: str, secret: k8s_client.V1Secret
) -> Workspace:
    ingresses = cast(
        List[k8s_client.V1Ingress],
        k8s_client.NetworkingV1Api()
        .list_namespaced_ingress(namespace=workspace_name)
        .items,
    )

    credentials: Dict[str, Any] = {
        k: base64.b64decode(v) for k, v in secret.data.items()
    }
    credentials["endpoint"] = config.S3_ENDPOINT
    credentials["region"] = config.S3_REGION

    container_registry_secret = fetch_secret(
        CONTAINER_REGISTRY_SECRET_NAME, namespace=workspace_name
    )

    return Workspace(
        status=WorkspaceStatus.ready,  # only ready workspaces can be serialized
        endpoints=[
            Endpoint(
                id=ingress.metadata.name,
                url=ingress.spec.rules[0].host,
            )
            for ingress in ingresses
        ],
        storage=Storage(
            credentials=credentials,
            # quota_in_mb=int(configmap.data["quota_in_mb"]),
        ),
        container_registry=ContainerRegistryCredentials(
            username=base64.b64decode(
                container_registry_secret.data["username"]
            ),
            password=base64.b64decode(
                container_registry_secret.data["password"]
            ),
        )
        if container_registry_secret
        else None,
    )


@app.delete("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
async def delete_workspace(workspace_name: str = workspace_path_type):
    # NOTE: name is validated via regex
    try:
        k8s_client.CoreV1Api().delete_namespace(workspace_name)
    except kubernetes.client.rest.ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
        else:
            raise

    return Response(status_code=HTTPStatus.NO_CONTENT)

    # TODO: this should clean up everything in namespace, anything else to consider?


# TODO: possibly set as base class of Storage, but wait until more details are known
class StorageUpdate(BaseModel):
    quota_in_mb: int


class WorkspaceUpdate(BaseModel):
    storage: Optional[StorageUpdate]


@app.patch("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
def patch_workspace(
    data: WorkspaceUpdate, workspace_name: str = workspace_path_type
):
    storage = data.storage
    if storage:  # noqa: E203
        k8s_client.CoreV1Api().patch_namespaced_config_map(
            name=config.WORKSPACE_CONFIG_MAP_NAME,
            namespace=workspace_name,
            # NOTE: config maps don't support ints!
            body={"data": {"quota_in_mb": str(storage.quota_in_mb)}},
        )

    return Response(status_code=HTTPStatus.NO_CONTENT)


@app.post(
    "/workspaces/{workspace_name}/redeploy", status_code=HTTPStatus.NO_CONTENT
)
def redeploy_workspace(
    background_tasks: BackgroundTasks, workspace_name: str = workspace_path_type
):
    if not namespace_exists(workspace_name):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    background_tasks.add_task(
        install_workspace_phase2, workspace_name=workspace_name, patch=True
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)


# Registration API


class Product(BaseModel):
    type: str
    url: str
    parent_identifier: Optional[str] = None


@app.post("/workspaces/{workspace_name}/register")
async def register(product: Product, workspace_name: str = workspace_path_type):

    k8s_namespace = workspace_name
    client = await aioredis.from_url(
        f"redis://{config.REDIS_SERVICE_NAME}.{k8s_namespace}:{config.REDIS_PORT}"
    )

    # get the URL and extract the path from the S3 URL
    try:
        # parsed_url = urlparse(product.url)
        # netloc = parsed_url.netloc
        # # if ":" in netloc:
        # #     netloc = netloc.rpartition(":")[2]
        # url = netloc + parsed_url.path
        url = product.url
    except Exception as e:
        message = {"message": f"Registration failed: {e}"}
        return JSONResponse(status_code=400, content=message)

    type_ = product.type.lower()
    if type_ == "stac-item":
        if url.endswith("/"):
            url = f"{url}catalog.json"
        await client.lpush(
            config.HARVESTER_QUEUE,
            json.dumps(
                {
                    "name": config.BUCKET_CATALOG_HARVESTER,
                    "values": {"resource": {"root_path": url}},
                }
            ),
        )
        message = f"STAC Catalog '{url}' was accepted for harvesting"
        logger.info(message)
        return JSONResponse(
            status_code=HTTPStatus.ACCEPTED, content={"message": message}
        )

    elif type_ in ("ades", "application"):
        if type_ == "ades":
            queue = config.REGISTER_ADES_QUEUE
        else:
            queue = config.REGISTER_APPLICATION_QUEUE

        await client.lpush(
            queue,
            json.dumps(
                {
                    "url": product.url,
                    "parent_identifier": product.parent_identifier,
                }
            ),
        )
        message = f"{product.type} {product.url} was applied for registration"
        logger.info(message)
        return JSONResponse(
            status_code=HTTPStatus.ACCEPTED, content={"message": message}
        )
        # TODO wait until registered?

    return Response(status_code=HTTPStatus.BAD_REQUEST)


class DeregisterProduct(BaseModel):
    type: str
    identifier: Optional[str]
    url: Optional[str]


@app.post("/workspaces/{workspace_name}/deregister")
async def deregister(
    deregister_product: DeregisterProduct,
    workspace_name: str = workspace_path_type,
):

    k8s_namespace = workspace_name
    client = await aioredis.from_url(
        f"redis://{config.REDIS_SERVICE_NAME}.{k8s_namespace}:{config.REDIS_PORT}"
    )

    if deregister_product.url:
        parsed_url = urlparse(deregister_product.url)
        netloc = parsed_url.netloc
        if ":" in netloc:
            netloc = netloc.rpartition(":")[2]
        url = netloc + parsed_url.path
        data = {"url": url}
    elif deregister_product.identifier:
        data = {"identifier": deregister_product.identifier}
    else:
        # TODO: return exception
        pass

    await client.lpush(config.DEREGISTER_QUEUE, json.dumps(data))
    # TODO: get result?

    message = {"message": f"Item '{data}' was successfully de-registered"}
    return JSONResponse(status_code=200, content=message)


@app.post("/workspaces/{workspace_name}/register-collection")
async def register_collection(
    collection: Dict[str, Any], workspace_name: str = workspace_path_type
):
    k8s_namespace = workspace_name
    client = await aioredis.from_url(
        f"redis://{config.REDIS_SERVICE_NAME}.{k8s_namespace}:{config.REDIS_PORT}"
    )

    await client.lpush(
        config.REGISTER_COLLECTION_QUEUE,
        json.dumps(collection),
    )
    message = f"{collection.get('id')} was applied for registration"
    logger.info(message)
    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED, content={"message": message}
    )


class CreateContainerRegistryRepository(BaseModel):
    repository_name: str


@app.post("/workspaces/{workspace_name}/create-container-registry-repository")
def create_container_registry_repository(
    data: CreateContainerRegistryRepository,
    workspace_name: str = workspace_path_type,
):
    # technically we only create a project, but repositories are autocreated when
    # you just push your docker image

    logger.info(f"Creating container repository {data.repository_name}")
    try:
        response = requests.post(
            f"{config.HARBOR_URL}/api/v2.0/projects",
            json={
                "project_name": data.repository_name,
            },
            auth=(config.HARBOR_ADMIN_USERNAME, config.HARBOR_ADMIN_PASSWORD),
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == HTTPStatus.CONFLICT:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail={"error": "Repository already exists"},
            )
        elif e.response.status_code == HTTPStatus.BAD_REQUEST:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail={"error": e.response.json().get("errors", [])},
            )
        else:
            raise

    # add workspace user as developer so they can push right away
    grant_container_registry_access(
        username=workspace_name,
        project_name=data.repository_name,
        role_id=2,  # Developer
    )

    return JSONResponse(status_code=HTTPStatus.NO_CONTENT, content="")


def grant_container_registry_access(
    username: str, project_name: str, role_id: int
) -> None:
    logger.info(
        f"Granting container registry access to {username} for {project_name}"
    )
    response = requests.post(
        f"{config.HARBOR_URL}/api/v2.0/projects/{project_name}/members",
        json={
            "member_user": {"username": username},
            "role_id": role_id,
        },
        auth=(config.HARBOR_ADMIN_USERNAME, config.HARBOR_ADMIN_PASSWORD),
    )
    response.raise_for_status()


class GrantAccess(BaseModel):
    repository_name: str
    username: str


@app.post("/grant-access-to-container-registry-repository")
def grant_container_registry_access_view(data: GrantAccess):
    # TODO: do we need more error handling?
    grant_container_registry_access(
        username=data.username,
        project_name=data.repository_name,
        role_id=5,  # limited guest
    )
    return JSONResponse(status_code=HTTPStatus.NO_CONTENT, content="")


def current_namespace() -> str:
    return open(
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    ).read()
