# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import json
import logging
import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from http import HTTPStatus
from typing import Any

import kubernetes.client
import kubernetes.client.rest
from fastapi import HTTPException, Path, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from slugify import slugify

from workspace_api import app, config, templates

from .models import (
    BucketAccessRequest,
    BucketPermission,
    ContainerRegistryCredentials,
    Credentials,
    Database,
    Datalab,
    Membership,
    MembershipRole,
    Storage,
    UserContext,
    Workspace,
    WorkspaceCreate,
    WorkspaceEdit,
    WorkspaceStatus,
)

logger = logging.getLogger(__name__)


def _with_prefix(name: str) -> str:
    p = (getattr(config, "PREFIX_FOR_NAME", "") or "").strip()
    p = p.rstrip("-")
    return f"{p}-{name}" if p else name


def _workspace_name_pattern() -> str:
    p = (getattr(config, "PREFIX_FOR_NAME", "") or "").strip().rstrip("-")
    if p:
        return rf"^{re.escape(p)}-"
    return r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat() if isinstance(ts, datetime) else str(ts)


WORKSPACE_NAME_PATTERN = _workspace_name_pattern()
workspace_path_type = Path(..., pattern=WORKSPACE_NAME_PATTERN)

API_PKG_INTERNAL = "pkg.internal/v1beta1"
KIND_STORAGE = "Storage"
KIND_DATALAB = "Datalab"
CRD_STORAGE = "storages.pkg.internal"
CRD_DATALAB = "datalabs.pkg.internal"


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


def current_namespace() -> str:
    try:
        return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read().strip()
    except FileNotFoundError:
        return "workspace"


def _dyn() -> DynamicClient:
    return DynamicClient(kubernetes.client.ApiClient())


def _res_required(api: str, kind: str) -> Any:
    try:
        return _dyn().resources.get(api_version=api, kind=kind)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={
                "error": f"Required CRD for kind {kind} ({api}) not available",
                "exception": str(e),
            },
        ) from e


def _res_optional(api: str, kind: str) -> Any:
    try:
        return _dyn().resources.get(api_version=api, kind=kind)
    except Exception:
        return None


def fetch_secret(secret_name: str, namespace: str) -> k8s_client.V1Secret | None:
    try:
        return k8s_client.CoreV1Api().read_namespaced_secret(
            name=secret_name,
            namespace=namespace,
        )
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        raise


def _to_b64_json(obj: Any) -> str:
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("utf-8")


def _crd_exists(name: str) -> bool:
    api = k8s_client.ApiextensionsV1Api()
    try:
        api.read_custom_resource_definition(name)
        return True  # noqa: TRY300
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return False
        raise


def _render_principal_placeholder(template: str | None, principal: str) -> str | None:
    if not template:
        return template
    s = str(template)
    return s.replace("<principal>", principal).replace("{principal}", principal)


def _storage_secret_name_for(principal: str) -> str | None:
    tmpl = getattr(config, "STORAGE_SECRET_NAME", None)
    return _render_principal_placeholder(tmpl, principal)


def _registry_secret_name_for(principal: str) -> str | None:
    tmpl = getattr(config, "CONTAINER_REGISTRY_SECRET_NAME", None)
    return _render_principal_placeholder(tmpl, principal)


@app.get(
    "/status",
    status_code=HTTPStatus.OK,
    tags=["System"],
    summary="Health and CRD availability",
    description=(
        "Reports service health and whether required/optional CRDs are present in the cluster.\n"
        "- Requires: `storages.pkg.internal`\n"
        "- Optional: `datalabs.pkg.internal`"
    ),
    responses={
        200: {"description": "Service healthy; returns CRD presence flags."},
        503: {"description": "Storage CRD missing; service not operational."},
    },
)
async def status() -> Response:
    storage_present = _crd_exists(CRD_STORAGE)
    datalab_present = _crd_exists(CRD_DATALAB)

    if not storage_present:
        return JSONResponse(
            {
                "ok": False,
                "error": f"Required CRD {CRD_STORAGE} not found in cluster",
                "datalab_crd_present": datalab_present,
            },
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    payload: dict[str, Any] = {
        "ok": True,
        "storage_crd_present": True,
        "datalab_crd_present": datalab_present,
    }
    if not datalab_present:
        payload["warnings"] = [f"Optional CRD {CRD_DATALAB} not found; memberships will be empty."]
    return JSONResponse(payload, status_code=HTTPStatus.OK)


def _get_cr(kind: str, name: str, required: bool) -> Any | None:
    api = _res_required(API_PKG_INTERNAL, kind) if required else _res_optional(API_PKG_INTERNAL, kind)
    if api is None:
        return None
    try:
        return api.get(name=name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        raise


def _to_spec_dict(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    spec = getattr(obj, "spec", None)
    if spec is None:
        return None
    return spec.to_dict() if hasattr(spec, "to_dict") else spec


def _get_container_registry_credentials(
    principal: str,
) -> ContainerRegistryCredentials | None:
    secret_name = _registry_secret_name_for(principal)
    if not secret_name:
        return None
    secret = fetch_secret(secret_name, current_namespace())
    if not secret or not secret.data:
        return None
    try:
        username = base64.b64decode(secret.data["username"]).decode()
        password = base64.b64decode(secret.data["password"]).decode()
        return ContainerRegistryCredentials(username=username, password=password)
    except (KeyError, binascii.Error) as e:
        logger.warning("Failed to decode container registry secret '%s': %s", secret_name, e)
        return None


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, int | float):
        return v != 0
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "on"}


def _get_first(*vals: Any) -> str | None:
    for v in vals:
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return None


def _bucketname_from(d: dict) -> str | None:
    return _get_first(
        d.get("bucketName"),
        d.get("bucket"),
    )


def _dedup_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _perm_from_str(s: str | None) -> BucketPermission:
    raw = (s or "none").strip().lower().replace("_", "").replace("-", "")

    match raw:
        case "none":
            return BucketPermission.NONE
        case "readwrite":
            return BucketPermission.READ_WRITE
        case "writeonly":
            return BucketPermission.WRITE_ONLY
        case "readonly":
            return BucketPermission.READ_ONLY
        case _:
            logger.warning("Unknown permission %r; defaulting to 'none'", s)
            return BucketPermission.NONE


def _extract_relevant_bucket_access_requests(
    discoverable_bucket_names: Sequence[str],
    current_principal: str,
    current_workspace_name: str,
) -> list[BucketAccessRequest]:
    try:
        storage_api = _res_required(API_PKG_INTERNAL, KIND_STORAGE)
        storages = storage_api.get(namespace=current_namespace())
        storage_items = getattr(storages, "items", []) or []
    except Exception as e:
        logger.warning("Failed listing storages: %s", e)
        storage_items = []

    def _spec_dict(obj: Any) -> dict:
        if hasattr(obj, "spec") and hasattr(obj.spec, "to_dict"):
            return obj.spec.to_dict() or {}
        return (getattr(obj, "spec", {}) or {}) if isinstance(getattr(obj, "spec", {}), dict) else {}

    out: list[BucketAccessRequest] = []

    for obj in storage_items:
        workspace_name = (getattr(obj.metadata, "name", None) or "").strip()
        spec = _spec_dict(obj)
        if not isinstance(spec, dict):
            continue

        principal = (spec.get("principal") or "").strip()
        if not principal:
            continue

        requests = spec.get("bucketAccessRequests") or []
        if isinstance(requests, list):
            for r in requests:
                if not isinstance(r, dict):
                    logger.warning("Skipping non-dict bucket access request: %r", r)
                    continue

                bucket_name = (r.get("bucketName") or "").strip()
                if not bucket_name:
                    continue
                if not (principal == current_principal or (bucket_name in discoverable_bucket_names)):
                    continue

                req_at = r.get("requestedAt")
                if not req_at:
                    logger.warning("Missing requestedAt for bucket %s; skipping.", bucket_name)
                    continue

                reason = (r.get("reason") or "").strip().lower()

                if "readonly" in reason or "read-only" in reason:
                    perm = BucketPermission.READ_ONLY
                elif "writeonly" in reason or "write-only" in reason:
                    perm = BucketPermission.WRITE_ONLY
                else:
                    perm = BucketPermission.READ_WRITE

                req = BucketAccessRequest(
                    workspace=workspace_name,
                    bucket=bucket_name,
                    permission=perm,
                    request_timestamp=req_at,
                    grant_timestamp=None,
                    denied_timestamp=None,
                )
                req._principal = principal  # noqa: SLF001
                out.append(req)

    existing_buckets_names = {bar.bucket for bar in out}
    for obj in storage_items:
        spec = _spec_dict(obj)
        if not isinstance(spec, dict):
            continue

        buckets = spec.get("buckets") or []
        if isinstance(buckets, list):
            for b in buckets:
                if not isinstance(b, dict) or not _as_bool(b.get("discoverable")):
                    continue

                bucket_name = (b.get("bucketName") or "").strip()
                if not bucket_name or bucket_name in existing_buckets_names or bucket_name in discoverable_bucket_names:
                    continue

                req = BucketAccessRequest(
                    workspace=current_workspace_name,
                    bucket=bucket_name,
                    permission=BucketPermission.READ_WRITE,
                    request_timestamp=None,
                    grant_timestamp=None,
                    denied_timestamp=None,
                )
                req._principal = current_principal  # noqa: SLF001
                out.append(req)
                existing_buckets_names.add(bucket_name)

    for obj in storage_items:
        workspace_name = (getattr(obj.metadata, "name", None) or "").strip()
        spec = _spec_dict(obj)
        if not isinstance(spec, dict):
            continue

        grants = spec.get("bucketAccessGrants") or []
        if isinstance(grants, list):
            for g in grants:
                if not isinstance(g, dict):
                    continue

                grantee = (g.get("grantee") or "").strip()
                bucket_name = (g.get("bucketName") or "").strip()
                if not grantee or not bucket_name:
                    continue

                granted_at = g.get("grantedAt") or g.get("granted_at")
                if not granted_at:
                    logger.warning(
                        "Skipping grant for grantee %s on bucket %s: missing grantedAt",
                        grantee,
                        bucket_name,
                    )
                    continue

                for existing in out:
                    if (
                        existing.bucket == bucket_name and existing._principal == grantee  # noqa: SLF001
                    ):
                        existing.request_timestamp = g.get("requestedAt") or granted_at
                        perm = _perm_from_str(g.get("permission"))
                        existing.grant_timestamp = granted_at if perm != BucketPermission.NONE else None
                        existing.denied_timestamp = granted_at if perm == BucketPermission.NONE else None
                        break

    return out


def _combine_workspace(request: Request, workspace_name: str) -> Workspace:
    storage_cr = _get_cr(KIND_STORAGE, workspace_name, required=True)
    if not storage_cr:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "error": f"Storage '{workspace_name}' not found",
                "crd": CRD_STORAGE,
            },
        )

    datalab_cr = _get_cr(KIND_DATALAB, workspace_name, required=False)

    storage_spec = _to_spec_dict(storage_cr) or {}
    datalab_spec = _to_spec_dict(datalab_cr) or {}

    principal = storage_spec.get("principal") or workspace_name

    buckets = storage_spec.get("buckets") or []
    all_buckets: list[str] = []
    discoverable_buckets: list[str] = []

    for it in buckets:
        bname = _bucketname_from(it or {}) or ""
        if not bname:
            continue
        all_buckets.append(bname)
        if _as_bool((it or {}).get("discoverable")):
            discoverable_buckets.append(bname)

    relevant_bucket_access_requests = _extract_relevant_bucket_access_requests(
        _dedup_preserve(discoverable_buckets), principal, workspace_name
    )

    users = (datalab_spec or {}).get("users") or []
    user_overrides = (datalab_spec or {}).get("userOverrides") or {}

    dl_created_at = getattr(getattr(datalab_cr, "metadata", None), "creationTimestamp", None)
    if not dl_created_at:
        dl_created_at = getattr(getattr(storage_cr, "metadata", None), "creationTimestamp", None)

    memberships = []
    first_owner_assigned = False

    for u in users:
        if not isinstance(u, str):
            continue
        member = u.strip()
        if not member:
            continue

        if not first_owner_assigned:
            role = MembershipRole.OWNER
            first_owner_assigned = True
        else:
            role_str = str((user_overrides.get(member) or {}).get("role") or "").strip().lower()
            role = MembershipRole.ADMIN if role_str == "admin" else MembershipRole.USER

        ts = (user_overrides.get(member) or {}).get("grantedAt") or dl_created_at

        memberships.append(
            Membership(
                member=member,
                role=role,
                creation_timestamp=_iso(ts),
            )
        )

    databases = []

    db_hosts = (datalab_spec or {}).get("databases") or {}

    if not isinstance(db_hosts, dict):
        db_hosts = {}

    seen_db: set[str] = set()

    for host_cfg in db_hosts.values():
        if not isinstance(host_cfg, dict):
            continue
        names = host_cfg.get("names") or []
        if not isinstance(names, list):
            continue
        for n in names:
            name = str(n or "").strip()
            if not name or name in seen_db:
                continue
            seen_db.add(name)
            databases.append(
                Database(
                    name=name,
                    creation_timestamp=_iso(dl_created_at),
                )
            )

    credentials = None
    secret = None
    storage_secret_name = _storage_secret_name_for(principal)
    if storage_secret_name:
        secret = fetch_secret(storage_secret_name, current_namespace())

    if secret and secret.data:
        try:
            envs = {k: base64.b64decode(v).decode("utf-8") for k, v in secret.data.items()}
            credentials = Credentials(
                bucketname=all_buckets[0] if buckets else (envs.get("BUCKET") or ""),
                access=envs.get(
                    "AWS_ACCESS_KEY_ID",
                    envs.get("access", envs.get("attribute.access", "")),
                ),
                secret=envs.get(
                    "AWS_SECRET_ACCESS_KEY",
                    envs.get("secret", envs.get("attribute.secret", "")),
                ),
                endpoint=envs.get(
                    "AWS_ENDPOINT_URL",
                    envs.get(
                        "endpoint",
                        envs.get("attribute.endpoint", getattr(config, "ENDPOINT", None)),
                    ),
                ),
                region=envs.get(
                    "AWS_REGION",
                    envs.get(
                        "region",
                        envs.get("attribute.region", getattr(config, "REGION", None)),
                    ),
                ),
            )
        except (KeyError, TypeError, binascii.Error) as e:
            logger.warning(
                "Error decoding credentials secret '%s': %s",
                getattr(secret.metadata, "name", "<unknown>"),
                e,
            )

    container_registry = _get_container_registry_credentials(principal)

    creation_timestamp = getattr(storage_cr.metadata, "creationTimestamp", None)
    version = storage_cr.metadata.resourceVersion
    workspace_status = WorkspaceStatus.READY if credentials else WorkspaceStatus.PROVISIONING

    storage = Storage(
        buckets=all_buckets,
        credentials=credentials,
        bucket_access_requests=relevant_bucket_access_requests,
    )
    datalab = Datalab(memberships=memberships, databases=databases)

    user_ctx = request.state.user

    username: str = user_ctx["username"]
    workspace_perms = set()
    if "*" in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"]["*"]
    if workspace_name in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"][workspace_name]

    return Workspace(
        name=workspace_name,
        creation_timestamp=creation_timestamp,
        version=version,
        status=workspace_status,
        storage=storage,
        datalab=datalab,
        container_registry=container_registry,
        user=UserContext(
            name=username,
            permissions=sorted(workspace_perms),
        ),
    )


@app.post(
    "/workspaces",
    status_code=HTTPStatus.CREATED,
    tags=["Workspaces"],
    summary="Create a new workspace",
    description=(
        "Creates a Storage resource and, if available, a Datalab resource for the given owner. "
        "Datalab sessions are created based on the configured session mode."
    ),
    responses={
        201: {"description": "Workspace created."},
        422: {"description": "Workspace with this name already exists or invalid input."},
        502: {"description": "Backend error while creating cluster resources."},
    },
)
async def create_workspace(data: WorkspaceCreate) -> dict[str, str]:
    safe_name = slugify(data.preferred_name, max_length=32) or str(uuid.uuid4())
    safe_owner = slugify(data.default_owner, max_length=32) or str(uuid.uuid4())
    workspace_name = _with_prefix(safe_name)[:63]

    storage_api = _res_required(API_PKG_INTERNAL, KIND_STORAGE)
    datalab_api = _res_optional(API_PKG_INTERNAL, KIND_DATALAB)

    try:
        storage_api.get(name=workspace_name, namespace=current_namespace())
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "Workspace with this name already exists"},
        )
    except ApiException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            raise

    try:
        storage_api.create(
            {
                "apiVersion": API_PKG_INTERNAL,
                "kind": KIND_STORAGE,
                "metadata": {"name": workspace_name},
                "spec": {
                    "principal": safe_owner,
                    "buckets": [{"bucketName": workspace_name, "discoverable": True}],
                },
            },
            namespace=current_namespace(),
        )
    except ApiException as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={
                "error": f"Failed to create Storage '{workspace_name}'",
                "exception": str(e),
            },
        ) from e

    if datalab_api is not None:
        session_mode = str(getattr(config, "SESSION_MODE", "on")).strip().lower()
        use_vcluster = _as_bool(getattr(config, "USE_VCLUSTER", "false"))
        try:
            datalab_api.create(
                {
                    "apiVersion": API_PKG_INTERNAL,
                    "kind": KIND_DATALAB,
                    "metadata": {"name": workspace_name},
                    "spec": {
                        "users": [safe_owner],
                        "secretName": _storage_secret_name_for(safe_owner),
                        "sessions": ["default"] if session_mode == "on" else [],
                        "vcluster": use_vcluster,
                    },
                },
                namespace=current_namespace(),
            )
        except ApiException as e:
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail={
                    "error": f"Failed to create Datalab '{workspace_name}'",
                    "exception": str(e),
                },
            ) from e

    return {"name": workspace_name}


def make_external_url(request: Request, path: str) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    prefix = (request.headers.get("x-forwarded-prefix") or "").rstrip("/")

    root_path = (request.scope.get("root_path") or "").rstrip("/")

    base = f"{scheme}://{host}{prefix or root_path}"
    if not path.startswith("/"):
        path = "/" + path
    return base + path


@app.get(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.OK,
    response_model=Workspace,
    response_model_exclude_none=True,
    tags=["Workspaces"],
    summary="Get a workspace",
    description=(
        "Returns a consolidated view of a workspace, including storage, memberships, "
        "status, and optional container registry credentials. If `Accept: text/html` and UI mode is enabled, "
        "returns an HTML page embedding the workspace data."
    ),
    responses={
        200: {"description": "Workspace details returned."},
        404: {"description": "Workspace not found."},
    },
)
async def get_workspace(request: Request, workspace_name: str = workspace_path_type) -> Response:
    ws = _combine_workspace(request, workspace_name)

    accept_header = request.headers.get("accept", "").lower()
    if (
        "text/html" in accept_header
        and templates is not None
        and (getattr(config, "UI_MODE", "no") == "ui" or request.query_params.get("devmode") == "true")
    ):
        workspace_data = _to_b64_json(ws.model_dump(mode="json", exclude_none=True))

        datalab_path = f"/workspaces/{workspace_name}/sessions/default"
        datalab_url = make_external_url(request, datalab_path)

        endpoints_data = _to_b64_json([{"id": "Datalab (default)", "url": datalab_url}])

        return templates.TemplateResponse(
            "ui.html",
            {
                "request": request,
                "base_path": request.url.path,
                "workspace_data": workspace_data,
                "endpoints_data": endpoints_data,
                "frontend_url": getattr(config, "FRONTEND_URL", "/ui/management"),
            },
        )
    return JSONResponse(ws.model_dump(mode="json", exclude_none=True), status_code=HTTPStatus.OK)


@app.put(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.ACCEPTED,
    tags=["Workspaces"],
    summary="Update a workspace",
    description=(
        "Patches workspace Storage (buckets and access requests/grants). "
        "If the Datalab CRD is present, can also add members to the Datalab."
    ),
    responses={
        202: {"description": "Update accepted and applied."},
        404: {"description": "Workspace not found."},
        502: {"description": "Backend error while patching cluster resources."},
    },
)
async def update_workspace(workspace_name: str, update: WorkspaceEdit) -> dict[str, str]:
    storage_api = _res_required(API_PKG_INTERNAL, KIND_STORAGE)

    try:
        storage_obj = storage_api.get(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise

    storage_spec = _to_spec_dict(storage_obj) or {}

    buckets = storage_spec.get("buckets") or []
    existing_names = {(_bucketname_from(b) or ""): b for b in buckets}
    for bname in update.add_buckets or []:
        if bname not in existing_names:
            buckets.append({"bucketName": bname, "discoverable": True})

    requests: list[dict] = storage_spec.get("bucketAccessRequests") or []
    grants: list[dict] = storage_spec.get("bucketAccessGrants") or []

    req_by_bucket: dict[str, dict] = {(r.get("bucketName") or "").strip(): r for r in requests if isinstance(r, dict)}
    gr_by_key: dict[tuple[str, str], dict] = {
        ((g.get("bucketName") or "").strip(), (g.get("grantee") or "").strip()): g for g in grants if isinstance(g, dict)
    }

    for p in update.patch_bucket_access_requests or []:
        bucket = (p.bucket or "").strip()
        if not bucket:
            continue

        if p.workspace == workspace_name:
            if bucket not in req_by_bucket:
                requests.append(
                    {
                        "bucketName": bucket,
                        "reason": "requesting access",
                        "requestedAt": _iso(p.request_timestamp),
                    }
                )
                req_by_bucket[bucket] = requests[-1]
            else:
                r = req_by_bucket[bucket]
                r.setdefault("requestedAt", _iso(p.request_timestamp))
        else:
            try:
                grantee_storage_obj = storage_api.get(name=p.workspace, namespace=current_namespace())
            except ApiException as e:
                logger.warning(
                    "patch_bucket_access_requests %s with invalid workspace (status=%s)",
                    p,
                    getattr(e, "status", None),
                )
                if e.status == HTTPStatus.NOT_FOUND:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail={"error": "invalid_workspace", "workspace": p.workspace},
                    ) from e
                raise HTTPException(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    detail={
                        "error": "backend_error",
                        "status": e.status,
                        "reason": getattr(e, "reason", None),
                    },
                ) from e

            grantee_storage_spec = _to_spec_dict(grantee_storage_obj) or {}
            grantee_principal = (grantee_storage_spec.get("principal") or "").strip()
            if not grantee_principal:
                logger.warning("patch_bucket_access_requests %s with no principal", p)
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"error": "missing_principal", "workspace": p.workspace},
                )

            key = (bucket, grantee_principal)
            g = gr_by_key.get(key)

            if p.denied_timestamp:
                perm = BucketPermission.NONE
                granted_at = _iso(p.denied_timestamp)
            elif p.grant_timestamp:
                perm = _perm_from_str(p.permission)
                granted_at = _iso(p.grant_timestamp)
            else:
                continue

            if g is None:
                g = {
                    "bucketName": bucket,
                    "grantee": grantee_principal,
                    "permission": perm,
                    "grantedAt": granted_at,
                }
                grants.append(g)
                gr_by_key[key] = g
            else:
                g["permission"] = perm
                g["grantedAt"] = granted_at

    storage_patch: dict[str, Any] = {
        "spec": {
            "buckets": buckets,
            "bucketAccessRequests": requests,
            "bucketAccessGrants": grants,
        }
    }

    try:
        storage_api.patch(
            name=workspace_name,
            namespace=current_namespace(),
            body=storage_patch,
            content_type="application/merge-patch+json",
        )
    except ApiException as e:
        logger.warning("Patching Storage '%s' failed: %s", workspace_name, e)
        raise
    except Exception as e:
        logger.warning("Patching Storage '%s' failed: %s", workspace_name, e)
        raise

    datalab_api = _res_optional(API_PKG_INTERNAL, KIND_DATALAB)

    add_memberships = update.add_memberships or []
    if add_memberships and datalab_api is None:
        logger.warning(
            "Datalab CRD not present; cannot add memberships for workspace '%s'.",
            workspace_name,
        )
    elif add_memberships:
        try:
            datalab_obj = datalab_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                logger.warning(
                    "Datalab resource '%s' not found; skipping membership additions.",
                    workspace_name,
                )
            else:
                logger.warning("Reading Datalab '%s' failed: %s", workspace_name, e)
            return {"name": workspace_name}
        except Exception as e:
            logger.warning("Reading Datalab '%s' failed: %s", workspace_name, e)
            return {"name": workspace_name}

        datalab_spec = _to_spec_dict(datalab_obj) or {}

        seen: set[str] = set()
        users: list[str] = []
        for m in datalab_spec.get("users") or []:
            if isinstance(m, str):
                ms = m.strip()
                if ms and ms not in seen:
                    seen.add(ms)
                    users.append(ms)

        user_overrides = datalab_spec.get("userOverrides") or {}
        if not isinstance(user_overrides, dict):
            user_overrides = {}

        for mem in add_memberships:
            member = (mem.member or "").strip()
            if not member:
                continue

            if member not in seen:
                seen.add(member)
                users.append(member)

            if users and member == users[0]:
                continue

            role = getattr(mem.role, "value", mem.role)
            role = (role or "").strip().lower()

            if role in ("admin", "user"):
                ov = user_overrides.get(member) or {}
                if not isinstance(ov, dict):
                    ov = {}

                ov["role"] = role

                if mem.creation_timestamp is not None:
                    ov["grantedAt"] = _iso(mem.creation_timestamp)

                user_overrides[member] = ov

        try:
            datalab_api.patch(
                name=workspace_name,
                namespace=current_namespace(),
                body={"spec": {"users": users, "userOverrides": user_overrides}},
                content_type="application/merge-patch+json",
            )
        except ApiException as e:
            logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
            raise
        except Exception as e:
            logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
            raise

    return {"name": workspace_name}


@app.delete(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.NO_CONTENT,
    tags=["Workspaces"],
    summary="Delete a workspace",
    description=("Deletes the Storage resource and, if present, the associated Datalab resource."),
    responses={
        204: {"description": "Workspace deleted."},
        404: {"description": "Workspace not found."},
    },
)
async def delete_workspace(workspace_name: str = workspace_path_type) -> Response:
    storage_api = _res_required(API_PKG_INTERNAL, KIND_STORAGE)
    datalab_api = _res_optional(API_PKG_INTERNAL, KIND_DATALAB)

    try:
        storage_api.delete(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise

    if datalab_api is not None:
        try:
            datalab_api.delete(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise

    return Response(status_code=HTTPStatus.NO_CONTENT)


POLL_INTERVAL_SECONDS = 10
MIN_DISPLAY_SECONDS = 3


@app.get(
    "/workspaces/{workspace_name}/sessions/{session_id}",
    status_code=HTTPStatus.OK,
    tags=["Sessions"],
    summary="Enable a session; JSON status or simple HTML waiter",
    description="On-demand session enablement. HTML: probe and wait. Non-HTML: 200 URL or 202 with Retry-After.",
    responses={
        200: {"description": "Ready: JSON with URL or minimal HTML waiter showing link and countdown."},
        202: {"description": 'Starting: JSON {"status":"starting"} with Retry-After: 10.'},
        404: {"description": "Workspace/session not found or enabling unavailable."},
        502: {"description": "Backend failure while enabling session."},
    },
)
async def get_workspace_session(
    request: Request,
    workspace_name: str = workspace_path_type,
    session_id: str = Path(..., description="Session identifier"),
) -> Response:
    datalab_api = _res_optional(API_PKG_INTERNAL, KIND_DATALAB)
    if datalab_api is None:
        msg = f"Session enabling unavailable: CRD {CRD_DATALAB} not found"
        logger.warning(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

    dl = _get_cr(KIND_DATALAB, workspace_name, required=False)
    if dl is None:
        msg = f"Session enabling failed: workspace '{workspace_name}' not found"
        logger.warning(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

    spec = _to_spec_dict(dl) or {}
    spec_sessions = [str(x) for x in (spec.get("sessions") or [])]
    if str(session_id) not in spec_sessions:
        session_mode = str(getattr(config, "SESSION_MODE", "on")).strip().lower()
        if session_mode == "auto" and str(session_id) == "default":
            new_sessions = list(dict.fromkeys([*spec_sessions, "default"]))
            logger.info(
                "Enabling session '%s' for workspace '%s' (auto mode).",
                session_id,
                workspace_name,
            )
            try:
                datalab_api.patch(
                    name=workspace_name,
                    namespace=current_namespace(),
                    body={"spec": {"sessions": new_sessions}},
                    content_type="application/merge-patch+json",
                )
            except ApiException as e:
                msg = f"Enabling session '{session_id}' for workspace '{workspace_name}' failed"
                logger.warning("%s: %s", msg, e)
                raise HTTPException(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    detail={"error": msg, "exception": str(e)},
                ) from e
        else:
            msg = f"Session enabling unavailable: session '{session_id}' not declared and auto mode is disabled"
            logger.info(msg)
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

    st = getattr(dl, "status", None)
    if st is None:
        st_dict: dict[str, Any] = {}
    elif isinstance(st, dict):
        st_dict = st
    elif hasattr(st, "to_dict"):
        st_dict = st.to_dict()  # type: ignore[no-any-return]
    else:
        st_dict = {}
    payload = (st_dict.get("sessions") or {}).get(str(session_id)) or {}
    url = payload.get("url") if isinstance(payload, dict) else None

    accept_header = request.headers.get("accept", "").lower()
    if "text/html" in accept_header:
        html = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Preparing session…</title>"
            "<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}"
            "p{padding:1em 2em;border-radius:4px;background:#eee;}</style>"
            "<p id='msg'>Preparing session, please wait…</p>"
            "<script>"
            f"const waitBefore={MIN_DISPLAY_SECONDS};"
            "const pollInterval=10000;"
            "function isHttp(u){try{const x=new URL(u);return x.protocol==='http:'||x.protocol==='https:';}catch{return false;}}"
            "function api(){const b=location.href.split('#')[0];const s=b.includes('?')?'&':'?';return b+s+'format=json&ts='+Date.now();}"
            "function checkUrl(url) {"
            "  document.getElementById('msg').textContent='Session is starting. Verifying...';"
            "  fetch(url, {method:'HEAD', cache:'no-store'})"
            "    .then(r => {"
            "      if (!r.ok) throw new Error('status:' + r.status);"
            "      document.getElementById('msg').innerHTML = `Session ready. Redirecting to <a href='${url}'>${url}</a>…`;"
            "      setTimeout(() => location.replace(url), waitBefore * 1000);"
            "    })"
            "    .catch(err => {"
            "      document.getElementById('msg').textContent='Session not ready yet. Will re-check shortly...';"
            "      setTimeout(check, pollInterval);"
            "    });"
            "}"
            "function check() {"
            "  fetch(api(),{headers:{'Accept':'application/json','Cache-Control':'no-store'},cache:'no-store'})"
            "    .then(r => r.status === 200 ? r.json() : Promise.reject(new Error('status:'+r.status)))"
            "    .then(d => {"
            "       if(d && d.url && isHttp(d.url)) { checkUrl(d.url); }"
            "       else { throw new Error('no-url'); }"
            "    })"
            "    .catch(e => {"
            "       document.getElementById('msg').textContent='Session not ready yet. Retrying...';"
            "       setTimeout(check, pollInterval);"
            "    });"
            "}"
            "check();"
            "</script>"
        )
        return HTMLResponse(html, status_code=HTTPStatus.OK, headers={"Cache-Control": "no-store"})

    if url:
        return JSONResponse(
            {"url": url},
            status_code=HTTPStatus.OK,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"status": "starting"},
        status_code=HTTPStatus.ACCEPTED,
        headers={
            "Retry-After": str(POLL_INTERVAL_SECONDS),
            "Cache-Control": "no-store",
        },
    )
