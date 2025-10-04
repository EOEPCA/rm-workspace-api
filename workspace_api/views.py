# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import json
import logging
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import kubernetes.client
import kubernetes.client.rest
from fastapi import HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
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
    Datalab,
    DatalabStatus,
    Membership,
    MembershipRole,
    Storage,
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
            detail={"error": f"Required CRD for kind {kind} ({api}) not available", "exception": str(e)},
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


@app.get("/status", status_code=HTTPStatus.OK)
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


def _get_container_registry_credentials(principal: str) -> ContainerRegistryCredentials | None:
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


def _extract_relevant_bucket_access_requests(  # noqa: C901, PLR0912, PLR0915
    wanted_bucket_names: Sequence[str],
    wanted_principal: str,
) -> list[BucketAccessRequest]:
    try:
        storage_api = _res_required(API_PKG_INTERNAL, KIND_STORAGE)
        storages = storage_api.get(namespace=current_namespace())
        storage_items = getattr(storages, "items", []) or []
    except Exception as e:
        logger.warning("Failed listing storages: %s", e)
        storage_items = []

    wanted_workspace = _with_prefix(wanted_principal)
    wanted_buckets = {b.strip() for b in (wanted_bucket_names or []) if isinstance(b, str) and b.strip()}

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
                if not (principal == wanted_principal or (bucket_name in wanted_buckets)):
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

                out.append(
                    BucketAccessRequest(
                        workspace=workspace_name,
                        bucket=bucket_name,
                        permission=perm,
                        request_timestamp=req_at,
                        grant_timestamp=None,
                        denied_timestamp=None,
                    )
                )

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
                if not bucket_name or bucket_name in existing_buckets_names or bucket_name in wanted_bucket_names:
                    continue

                out.append(
                    BucketAccessRequest(
                        workspace=wanted_workspace,
                        bucket=bucket_name,
                        permission=BucketPermission.READ_WRITE,
                        request_timestamp=None,
                        grant_timestamp=None,
                        denied_timestamp=None,
                    )
                )
                existing_buckets_names.add(bucket_name)

    for obj in storage_items:
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

                grantee_workspace = _with_prefix(grantee)
                granted_at = g.get("grantedAt") or g.get("granted_at")
                if not granted_at:
                    logger.warning("Skipping grant for grantee %s on bucket %s: missing grantedAt", grantee_workspace, bucket_name)
                    continue

                for existing in out:
                    if existing.bucket == bucket_name and existing.workspace == grantee_workspace:
                        existing.request_timestamp = g.get("requestedAt") or granted_at
                        perm = _perm_from_str(g.get("permission"))
                        existing.grant_timestamp = granted_at if perm != BucketPermission.NONE else None
                        existing.denied_timestamp = granted_at if perm == BucketPermission.NONE else None
                        break

    return out


def _combine_workspace(workspace_name: str) -> Workspace:
    storage_cr = _get_cr(KIND_STORAGE, workspace_name, required=True)
    if not storage_cr:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={"error": f"Storage '{workspace_name}' not found", "crd": CRD_STORAGE},
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

    relevant_bucket_access_requests = _extract_relevant_bucket_access_requests(_dedup_preserve(discoverable_buckets), principal)

    users = (datalab_spec or {}).get("users") or []
    now = datetime.now(UTC)
    memberships = [
        Membership(
            member=u.strip(),
            role=MembershipRole.OWNER if u == principal else MembershipRole.CONTRIBUTOR,
            creation_timestamp=now,
        )
        for u in users
        if isinstance(u, str) and u.strip()
    ]

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
                access=envs.get("AWS_ACCESS_KEY_ID", envs.get("access", envs.get("attribute.access", ""))),
                secret=envs.get("AWS_SECRET_ACCESS_KEY", envs.get("secret", envs.get("attribute.secret", ""))),
                endpoint=envs.get(
                    "AWS_ENDPOINT_URL", envs.get("endpoint", envs.get("attribute.endpoint", getattr(config, "ENDPOINT", None)))
                ),
                region=envs.get("AWS_REGION", envs.get("region", envs.get("attribute.region", getattr(config, "REGION", None)))),
            )
        except (KeyError, TypeError, binascii.Error) as e:
            logger.warning("Error decoding credentials secret '%s': %s", getattr(secret.metadata, "name", "<unknown>"), e)

    container_registry = _get_container_registry_credentials(principal)

    creation_timestamp = getattr(storage_cr.metadata, "creationTimestamp", None)
    version = storage_cr.metadata.resourceVersion
    workspace_status = WorkspaceStatus.READY if credentials else WorkspaceStatus.PROVISIONING

    sessions = (datalab_spec or {}).get("sessions") or []

    session_mode = str(getattr(config, "SESSION_MODE", "on")).strip().lower()

    if sessions:
        datalab_status = DatalabStatus.ALWAYS_ON
    elif session_mode == "auto":
        datalab_status = DatalabStatus.ON_DEMAND
    else:
        datalab_status = DatalabStatus.DISABLED

    storage = Storage(
        buckets=all_buckets,
        credentials=credentials,
        bucket_access_requests=relevant_bucket_access_requests,
    )
    datalab = Datalab(memberships=memberships, status=datalab_status)

    return Workspace(
        name=workspace_name,
        creation_timestamp=creation_timestamp,
        version=version,
        status=workspace_status,
        storage=storage,
        datalab=datalab,
        container_registry=container_registry,
    )


@app.post("/workspaces", status_code=HTTPStatus.CREATED)
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
            detail={"error": f"Failed to create Storage '{workspace_name}'", "exception": str(e)},
        ) from e

    if datalab_api is not None:
        auto_mode = _as_bool(getattr(config, "SESSION_MODE", "on"))
        use_vcluster = _as_bool(getattr(config, "USE_VCLUSTER", "false"))
        try:
            datalab_api.create(
                {
                    "apiVersion": API_PKG_INTERNAL,
                    "kind": KIND_DATALAB,
                    "metadata": {"name": workspace_name},
                    "spec": {
                        "users": [safe_owner],
                        "sessions": [] if auto_mode else ["default"],
                        "vcluster": use_vcluster,
                    },
                },
                namespace=current_namespace(),
            )
        except ApiException as e:
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail={"error": f"Failed to create Datalab '{workspace_name}'", "exception": str(e)},
            ) from e

    return {"name": workspace_name}


@app.get(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.OK,
    response_model=Workspace,
    response_model_exclude_none=True,
)
async def get_workspace(request: Request, workspace_name: str = workspace_path_type) -> Response:
    ws = _combine_workspace(workspace_name)

    accept_header = request.headers.get("accept", "")
    if (
        "text/html" in accept_header
        and templates is not None
        and (getattr(config, "UI_MODE", "no") == "ui" or request.query_params.get("devmode") == "true")
    ):
        workspace_data = _to_b64_json(ws.model_dump(mode="json", exclude_none=True))
        return templates.TemplateResponse(
            "ui.html",
            {
                "request": request,
                "base_path": request.url.path,
                "workspace_data": workspace_data,
                "frontend_url": getattr(config, "FRONTEND_URL", "/ui/management"),
            },
        )
    return JSONResponse(ws.model_dump(mode="json", exclude_none=True), status_code=HTTPStatus.OK)


@app.put("/workspaces/{workspace_name}", status_code=HTTPStatus.ACCEPTED)
async def update_workspace(workspace_name: str, update: WorkspaceEdit) -> dict[str, str]:  # noqa: C901, PLR0912, PLR0915
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
            grantee_principal = p.workspace
            prefix = (getattr(config, "PREFIX_FOR_NAME", "") or "").strip().rstrip("-")
            if p and p.workspace.startswith(prefix + "-"):
                grantee_principal = p.workspace[len(prefix) + 1 :]

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
    if (update.add_members or []) and datalab_api is None:
        logger.warning("Datalab CRD not present; cannot add members for workspace '%s'.", workspace_name)
    elif update.add_members:
        try:
            datalab_obj = datalab_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                logger.warning("Datalab resource '%s' not found; skipping member additions.", workspace_name)
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

        for m in update.add_members or []:
            ms = (m or "").strip()
            if ms and ms not in seen:
                seen.add(ms)
                users.append(ms)

        try:
            datalab_api.patch(
                name=workspace_name,
                namespace=current_namespace(),
                body={"spec": {"users": users}},
                content_type="application/merge-patch+json",
            )
        except ApiException as e:
            logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
            raise
        except Exception as e:
            logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
            raise

    return {"name": workspace_name}


@app.delete("/workspaces/{workspace_name}", status_code=HTTPStatus.NO_CONTENT)
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
