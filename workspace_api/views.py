from __future__ import annotations

import base64
import enum
from http import HTTPStatus
import uuid
from typing import cast, Optional, List, Dict
import asyncio
from urllib.parse import urlparse
import logging
import json

from fastapi import HTTPException, Path, Response, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from kubernetes.client.models.v1_secret import V1Secret
import kubernetes.client.rest
import kubernetes.watch
from kubernetes import config as k8s_config, client as k8s_client
from slugify import slugify
from pydantic import BaseModel
import aioredis

from workspace_api import app, config


# TODO: fix logging output with gunicorn
logger = logging.getLogger(__name__)


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

    background_tasks.add_task(
        install_workspace_phase2,
        workspace_name=workspace_name,
    )

    return {"name": workspace_name}


def create_bucket(workspace_name: str) -> None:
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


def install_workspace_phase2(workspace_name, patch=False) -> None:
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

    domain = config.WORKSPACE_DOMAIN
    ingress_host = f"data-access.{workspace_name}.{domain}"
    pycsw_server_url = f"resource-catalogue.{workspace_name}.{domain}"
    bucket = base64.b64decode(
        secret.data["bucketname"]
    ).decode()
    projectid = base64.b64decode(
        secret.data["projectid"]
    ).decode()

    values = {
        "vs": {
            "ingress": {
                "hosts": [
                    {
                        "host": ingress_host,
                    },
                ],
                "tls": [
                    {
                        "hosts": [ingress_host],
                        "secretName": "data-access-tls",
                    }
                ],
            },
            "config": {
                "objectStorage": {
                    "data": {
                        "data": {
                            # TODO: this values are secret, pass them as secret
                            "access_key_id": base64.b64decode(
                                secret.data["access"]
                            ).decode(),
                            "secret_access_key": base64.b64decode(
                                secret.data["secret"]
                            ).decode(),
                            "bucket": bucket,
                            "endpoint_url": config.S3_ENDPOINT,
                            "region": config.S3_REGION,
                        },
                    },
                },
                "registrar": {
                    "backends": [{
                        "path": "registrar.backend.EOxServerBackend",
                        "schemes": [
                            "stac-item"
                        ],
                        "kwargs": {
                            "instance_base_path": "/var/www/pvs/dev",
                            "instance_name": "pvs_instance",
                            # TODO: delete this mapping after the Demo and
                            # figure out a better way to go forward
                            "mapping": {
                                '': {
                                    '': {
                                        'product_type_name': \
                                        'nhi1_nhi1_bitmask_nhi2_nhi2_bitmask',
                                        'coverages': {
                                            'nhi1': 'nhi1',
                                            'nhi1_bitmask': 'nhi1_bitmask',
                                            'nhi2': 'nhi2',
                                            'nhi2_bitmask': 'nhi2_bitmask',
                                        },
                                        'collections': ['DATA']
                                    },
                                }
                            },
                        },
                    }, {
                        "path": "registrar_pycsw.backend.PycswBackend",
                        "kwargs": {
                            "repository_database_uri": (
                                "postgresql://postgres:mypass@resource-catalogue-db/pycsw"
                            ),
                            "ows_url": f"https://{ingress_host}/ows",
                            "public_s3_url": (
                                f'{config.S3_ENDPOINT}/{projectid}:{bucket}'
                            ),
                        },
                    }],
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
                        "url": f"http://{pycsw_server_url}",
                    },
                },
            },
            "ingress": {
                "host": pycsw_server_url,
                "tls_host": pycsw_server_url,
            }
        },
        "global": {
            "namespace": workspace_name,
        },
    }

    group = "helm.toolkit.fluxcd.io"
    version = "v2beta1"
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

    api = k8s_client.CustomObjectsApi()

    if patch:
        response = api.list_namespaced_custom_object(
            group=group,
            plural="helmreleases",
            version=version,
            namespace=workspace_name,
        )
        found_hr = False
        for item in response['items']:
            try:
                if item['spec']['releaseName'] == 'workspace':
                    found_hr = True
                    break

            except KeyError:
                pass

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
            return

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


class Workspace(BaseModel):
    status: WorkspaceStatus

    # NOTE: these are defined iff the workspace is ready
    endpoints: List[Endpoint] = []
    storage: Optional[Storage]


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
        List[k8s_client.ExtensionsV1beta1Ingress],
        k8s_client.ExtensionsV1beta1Api()
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
    credentials = {k: base64.b64decode(v) for k, v in secret.data.items()}
    credentials["endpoint"] = config.S3_ENDPOINT
    credentials["region"] = config.S3_REGION

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
    if (storage := data.storage) :  # noqa: E203
        k8s_client.CoreV1Api().patch_namespaced_config_map(
            name=config.WORKSPACE_CONFIG_MAP_NAME,
            namespace=workspace_name,
            # NOTE: config maps don't support ints!
            body={"data": {"quota_in_mb": str(storage.quota_in_mb)}},
        )

    return Response(status_code=HTTPStatus.NO_CONTENT)


@app.post("/workspaces/{workspace_name}/redeploy", status_code=HTTPStatus.NO_CONTENT)
def redeploy_workspace(background_tasks: BackgroundTasks,
                       workspace_name: str = workspace_path_type):
    if not namespace_exists(workspace_name):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    background_tasks.add_task(
        install_workspace_phase2,
        workspace_name=workspace_name,
        patch=True
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)


# Registration API


class Product(BaseModel):
    type: str
    url: str


@app.post("/workspaces/{workspace_name}/register")
async def register(product: Product,
                   workspace_name: str = workspace_path_type):

    k8s_namespace = workspace_name
    client = await aioredis.create_redis(
        # TODO: make this configurable of better
        (f"workspace-redis-master.{k8s_namespace}", config.REDIS_PORT),
        encoding="utf-8"
    )

    # get the URL and extract the path from the S3 URL
    try:
        parsed_url = urlparse(product.url)
        netloc = parsed_url.netloc
        if ':' in netloc:
            netloc = netloc.rpartition(':')[2]
        url = netloc + parsed_url.path

        await client.lpush(config.REGISTER_QUEUE, url)

        time_index = 0.0
        while True:
            logger.info("Product '%s' is being proccessed!" % url)
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
            logger.info("Item '%s' was successfully registered" % url)
            message = {"message": f"Item '{url}' was successfully registered"}
            return JSONResponse(status_code=200, content=message)

        elif await client.sismember(config.FAILURE_SET, url):
            logger.info("Failed to register product %s" % url)
            message = {"message": f"Failed to register product {url}"}
            return JSONResponse(status_code=400, content=message)

    except Exception as e:
        message = {"message": f"Registration failed: {e}"}
        return JSONResponse(status_code=400, content=message)


class DeregisterProduct(BaseModel):
    identifier: Optional[str]
    url: Optional[str]


@app.post("/workspaces/{workspace_name}/deregister")
async def deregister(deregister_product: DeregisterProduct,
                     workspace_name: str = workspace_path_type):

    k8s_namespace = workspace_name
    client = await aioredis.create_redis(
        # TODO: make this configurable of better
        (f"workspace-redis-master.{k8s_namespace}", config.REDIS_PORT),
        encoding="utf-8"
    )

    if deregister_product.url:
        parsed_url = urlparse(deregister_product.url)
        netloc = parsed_url.netloc
        if ':' in netloc:
            netloc = netloc.rpartition(':')[2]
        url = netloc + parsed_url.path
        data = {'url': url}
    elif deregister_product.identifier:
        data = {'identifier': deregister_product.identifier}
    else:
        # TODO: return exception
        pass

    await client.lpush(config.DEREGISTER_QUEUE, json.dumps(data))
    # TODO: get result?

    message = {"message": f"Item '{data}' was successfully de-registered"}
    return JSONResponse(status_code=200, content=message)
