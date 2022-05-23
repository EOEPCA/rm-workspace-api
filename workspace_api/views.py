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
async def create_workspace(data: WorkspaceCreate, background_tasks: BackgroundTasks):

    workspace_name = workspace_name_from_preferred_name(data.preferred_name)

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

    create_bucket(workspace_name=workspace_name)

    create_uma_client_credentials_secret(workspace_name=workspace_name)

    create_harbor_user(workspace_name=workspace_name)

    background_tasks.add_task(
        install_workspace_phase2,
        workspace_name=workspace_name,
        default_owner=data.default_owner,
    )

    return {"name": workspace_name}


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

        if event_type == "ADDED" and event_secret_name == config.WORKSPACE_SECRET_NAME:
            logger.info("Found the secret we were looking for")
            watch.stop()
            return event_secret

    raise Exception("Watch aborted")


def install_workspace_phase2(workspace_name, default_owner=None, patch=False) -> None:
    """Wait for secret, then install helm chart"""
    secret = wait_for_namespace_secret(workspace_name=workspace_name)

    logger.info(f"Install phase 2 for {workspace_name}")

    chart = {
        "spec": {
            "chart": config.HELM_CHART_NAME,
            "version": config.HELM_CHART_VERSION,
            "sourceRef": {
                "kind": "HelmRepository",
                "name": config.GIT_REPO_RESOURCE_FOR_HELM_CHART_NAME,
                "namespace": config.GIT_REPO_RESOURCE_FOR_HELM_CHART_NAMESPACE,
            },
        }
    }

    api = k8s_client.CustomObjectsApi()
    group = "helm.toolkit.fluxcd.io"
    version = "v2beta1"

    domain = config.WORKSPACE_DOMAIN
    data_access_host = f"data-access.{workspace_name}.{domain}"
    catalog_host = f"resource-catalogue.{workspace_name}.{domain}"
    bucket = base64.b64decode(secret.data["bucketname"]).decode()
    projectid = base64.b64decode(secret.data["projectid"]).decode()

    found_hr = False
    if patch:
        response = api.list_namespaced_custom_object(
            group=group,
            plural="helmreleases",
            version=version,
            namespace=workspace_name,
        )
        found_hr = False
        for item in response["items"]:
            try:
                if item["spec"]["releaseName"] == "workspace":
                    found_hr = True
                    default_owner = item["spec"]["values"]["resource-guard"][
                        "pep-engine"
                    ]["customDefaultResources"][0]["default_owner"]
                    break

            except KeyError:
                pass
    access_key_id = base64.b64decode(secret.data["access"]).decode()
    secret_access_key = base64.b64decode(secret.data["secret"]).decode()
    values = {
        "vs": {
            # open ingresses are now disabled
            # "ingress": {
            #     "hosts": [
            #         {
            #             "host": data_access_open_host,
            #         },
            #     ],
            #     "tls": [
            #         {
            #             "hosts": [data_access_open_host],
            #             "secretName": "data-access-tls",
            #         }
            #     ],
            # },
            "global": {
                "storage": {
                    "data": {
                        "data": {
                            # TODO: this values are secret, pass them as secret
                            "access_key_id": access_key_id,
                            "secret_access_key": secret_access_key,
                            "bucket": bucket,
                            "endpoint_url": config.S3_ENDPOINT,
                            "region": config.S3_REGION,
                        },
                    },
                },
            },
            "harvester": {
                "config": {
                    "harvesters": [
                        {
                            "name": config.BUCKET_CATALOG_HARVESTER,
                            "resource": {
                                "type": "STACCatalog",
                                "source": {
                                    "type": "S3",
                                    "bucket": bucket,
                                    "access_key_id": access_key_id,
                                    "secret_access_key": secret_access_key,
                                    "endpoint_url": config.S3_ENDPOINT,
                                    "region_name": config.S3_REGION,
                                    "validate_bucket_name": False,
                                    "public": False,
                                },
                            },
                            "queue": "register_queue",
                        },
                    ],
                },
            },
            "registrar": {
                "config": {
                    "backends": [
                        {
                            "path": "registrar.backend.eoxserver.EOxServerBackend",
                            "kwargs": {
                                "instance_base_path": "/var/www/pvs/dev",
                                "instance_name": "pvs_instance",
                                "product_types": [],
                                "auto_create_product_types": True,
                            }
                        },
                        {
                            "path": "registrar_pycsw.backend.PycswItemBackend",
                            "kwargs": {
                                "repository_database_uri": (
                                    "postgresql://postgres:mypass@resource-catalogue-db/pycsw"
                                ),
                                "ows_url": f"https://{data_access_host}/ows",
                                "public_s3_url": (
                                    f"{config.S3_ENDPOINT}/{projectid}:{bucket}"
                                ),
                            },
                        },
                    ],
                    "pathBackends": [
                        {
                            "path": "registrar_pycsw.backend.PycswCWLBackend",
                            "kwargs": {
                                "repository_database_uri": (
                                    "postgresql://postgres:mypass@resource-catalogue-db/pycsw"
                                ),
                                "ows_url": f"https://{data_access_host}/ows",
                                "public_s3_url": (
                                    f"{config.S3_ENDPOINT}/{projectid}:{bucket}"
                                ),
                            },
                        },
                    ],
                },
            },
        },
        "rm-resource-catalogue": {
            "global": {
                "namespace": workspace_name,
            },
            "pycsw": {
                "config": {
                    "server": {
                        "url": f"https://{catalog_host}",
                    },
                },
            },
        },
        "resource-guard": {
            "global": {
                "pep": f"{workspace_name}-pep",
                "domain": config.WORKSPACE_DOMAIN,
                "nginxIp": config.AUTH_SERVER_IP,
                "certManager": {
                    "clusterIssuer": config.CLUSTER_ISSUER,
                },
                "context": f"{workspace_name}-resource-guard",
            },
            "pep-engine": {
                "configMap": {
                    "workingMode": "PARTIAL",
                    "asHostname": config.AUTH_SERVER_HOSTNAME,
                    "pdpHostname": config.AUTH_SERVER_HOSTNAME,
                },
                "nginxIntegration": {
                    "enabled": False
                    # hostname: resource-catalogue-auth
                },
                # image:
                #   pullPolicy: Always
                "volumeClaim": {
                    "name": f"eoepca-resman-pvc-{workspace_name}",
                    "create": "true",
                },
                "defaultResources": [
                    {
                        "name": f"Workspace {workspace_name}",
                        "description": "Root URL of a users workspace",
                        "resource_uri": "/",
                        "scopes": [],
                        "default_owner": default_owner,
                    }
                ],
            },
            "uma-user-agent": {
                "fullnameOverride": f"{workspace_name}-agent",
                # image:
                #   tag: latest
                #   pullPolicy: Always
                "nginxIntegration": {
                    "enabled": True,
                    "hosts": [
                        {
                            "host": f"resource-catalogue.{workspace_name}",
                            "paths": [
                                {
                                    "path": "/(.*)",
                                    "service": {
                                        "name": "resource-catalogue-service",
                                        "port": 80,
                                    },
                                },
                            ],
                        },
                        {
                            "host": f"data-access.{workspace_name}",
                            "paths": [
                                {
                                    "path": "/(ows.*)",
                                    "service": {
                                        "name": "workspace-renderer",
                                        "port": 80,
                                    },
                                },
                                {
                                    "path": "/(opensearch.*)",
                                    "service": {
                                        "name": "workspace-renderer",
                                        "port": 80,
                                    },
                                },
                                {
                                    "path": "/(admin.*)",
                                    "service": {
                                        "name": "workspace-renderer",
                                        "port": 80,
                                    },
                                },
                                {
                                    "path": "/cache/(.*)",
                                    "service": {
                                        "name": "workspace-cache",
                                        "port": 80,
                                    },
                                },
                                {
                                    "path": "/(.*)",
                                    "service": {
                                        "name": "workspace-client",
                                        "port": 80,
                                    },
                                },
                            ],
                        },
                    ],
                    "annotations": {
                        "nginx.ingress.kubernetes.io/proxy-read-timeout": "600",
                        "nginx.ingress.kubernetes.io/enable-cors": "true",
                        "nginx.ingress.kubernetes.io/rewrite-target": "/$1",
                    },
                },
                "client": {
                    "credentialsSecretName": config.UMA_CLIENT_SECRET_NAME,
                },
                "logging": {
                    "level": "info",
                },
                "unauthorizedResponse": f'Bearer realm="https://portal.{config.WORKSPACE_DOMAIN}/oidc/authenticate/"',  # TODO: correct domain
                # "openAccess": True,
            },
        },
        "global": {
            "namespace": workspace_name,
        },
        "storage": {
            "storageClassName": config.HELM_CHART_STORAGE_CLASS_NAME
        },
    }

    body = {
        "apiVersion": f"{group}/{version}",
        "kind": "HelmRelease",
        "metadata": {
            "name": "workspace",
            "namespace": workspace_name,
        },
        "spec": {
            "chart": chart,
            "interval": "1h0m0s",
            "releaseName": "workspace",
            "targetNamespace": workspace_name,
            "values": values,
        },
    }

    # try patching the HR first
    if found_hr:
        api.patch_namespaced_custom_object(
            name="workspace",
            group=group,
            plural="helmreleases",
            version=version,
            namespace=workspace_name,
            body=body,
        )
    else:
        # fallback to (re-)create the HR
        api.create_namespaced_custom_object(
            group=group,
            plural="helmreleases",
            version=version,
            namespace=workspace_name,
            body=body,
        )


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


def serialize_workspace(workspace_name: str, secret: k8s_client.V1Secret) -> Workspace:
    ingresses = cast(
        List[k8s_client.V1Ingress],
        k8s_client.NetworkingV1Api()
        .list_namespaced_ingress(namespace=workspace_name)
        .items,
    )

    # current workspace chart doesn't feature a configmap
    """
    configmap = cast(
        k8s_client.V1ConfigMap,
        k8s_client.CoreV1Api().read_namespaced_config_map(
            config.WORKSPACE_CONFIG_MAP_NAME,
            namespace=workspace_name,
        ),
    )
    """
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
            username=base64.b64decode(container_registry_secret.data["username"]),
            password=base64.b64decode(container_registry_secret.data["password"]),
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
def patch_workspace(data: WorkspaceUpdate, workspace_name: str = workspace_path_type):
    storage = data.storage
    if storage:  # noqa: E203
        k8s_client.CoreV1Api().patch_namespaced_config_map(
            name=config.WORKSPACE_CONFIG_MAP_NAME,
            namespace=workspace_name,
            # NOTE: config maps don't support ints!
            body={"data": {"quota_in_mb": str(storage.quota_in_mb)}},
        )

    return Response(status_code=HTTPStatus.NO_CONTENT)


@app.post("/workspaces/{workspace_name}/redeploy", status_code=HTTPStatus.NO_CONTENT)
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


@app.post("/workspaces/{workspace_name}/register")
async def register(product: Product, workspace_name: str = workspace_path_type):

    k8s_namespace = workspace_name
    client = await aioredis.from_url(
        f"redis://workspace-redis-master.{k8s_namespace}:{config.REDIS_PORT}"
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

    # TODO:
    if product.type == "stac-item":
        if url.endswith("/"):
            url = f"{url}catalog.json"
        await client.lpush(
            config.HARVESTER_QUEUE,
            json.dumps({
                "name": config.BUCKET_CATALOG_HARVESTER,
                "values": {
                    "resource": {
                        "root_path": url
                    }
                }
            })
        )
        logger.info(f"STAC Catalog '{url}' was accepted for harvesting")
        message = {"message": f"STAC Catalog '{url}' was accepted for harvesting"}
        return JSONResponse(status_code=202, content=message)

    # Register CWL applications
    try:
        await client.lpush(config.REGISTER_PATH_QUEUE, url)
        time_index = 0.0
        while True:
            logger.info("CWL file '%s' is being proccessed!" % url)
            await asyncio.sleep(config.REGISTRATION_CHECK_INTERVAL)
            time_index += config.REGISTRATION_CHECK_INTERVAL
            if (
                time_index >= config.REGISTRATION_TIME_OUT
                or not await client.sismember(config.PROGRESS_SET, url)
            ):
                break

        if time_index >= config.REGISTRATION_TIME_OUT:
            logger.info("Timeout while registering '%s'" % url)
            message = {"message": f"Timeout while registering '{url}'"}
            return JSONResponse(status_code=400, content=message)

        if await client.sismember(config.SUCCESS_SET, url):
            logger.info("CWL file '%s' was successfully registered" % url)
            message = {"message": f"CWL file '{url}' was successfully registered"}
            return JSONResponse(status_code=200, content=message)

        elif await client.sismember(config.FAILURE_SET, url):
            logger.info("Failed to register CWL file %s" % url)
            message = {"message": f"Failed to register CWL file {url}"}
            return JSONResponse(status_code=400, content=message)

    except Exception as e:
        message = {"message": f"Registration failed: {e}"}
        return JSONResponse(status_code=400, content=message)


class DeregisterProduct(BaseModel):
    identifier: Optional[str]
    url: Optional[str]


@app.post("/workspaces/{workspace_name}/deregister")
async def deregister(
    deregister_product: DeregisterProduct, workspace_name: str = workspace_path_type
):

    k8s_namespace = workspace_name
    client = await aioredis.create_redis(
        # TODO: make this configurable of better
        (f"workspace-redis-master.{k8s_namespace}", config.REDIS_PORT),
        encoding="utf-8",
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

    return JSONResponse(status_code=HTTPStatus.NO_CONTENT)


def grant_container_registry_access(
    username: str, project_name: str, role_id: int
) -> None:
    logger.info(f"Granting container registry access to {username} for {project_name}")
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
    return JSONResponse(status_code=HTTPStatus.NO_CONTENT)


def current_namespace() -> str:
    return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()
