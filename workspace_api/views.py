# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import hashlib
import html
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import kubernetes.client
import kubernetes.client.rest
import requests
from authlib.jose import JoseError, JsonWebToken
from fastapi import HTTPException, Path, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from kubernetes.utils.quantity import parse_quantity
from pydantic import ValidationError
from slugify import slugify

from workspace_api import app, config, templates

from .models import (
    RESOURCE_NAME_PATTERN,
    SESSION_NAME_PATTERN,
    Bucket,
    BucketAccessRequest,
    BucketLifecycleRule,
    BucketLifecycleRuleMode,
    BucketPermission,
    Connection,
    CredentialReference,
    Credentials,
    Datalab,
    Membership,
    MembershipRole,
    OAuth2Connection,
    Session,
    SessionCreate,
    SessionState,
    SessionStateUpdate,
    Storage,
    Store,
    StoreType,
    UserContext,
    UserPermission,
    VCluster,
    VClusterGroup,
    VClusterGroupCreate,
    Workspace,
    WorkspaceCreate,
    WorkspaceEdit,
    WorkspaceListItem,
    WorkspaceListSession,
    WorkspaceStatus,
    WorkspaceToken,
    validate_resource_name,
)

logger = logging.getLogger(__name__)


def _with_prefix(name: str) -> str:
    p = (config.PREFIX_FOR_NAME or "").strip()
    p = p.rstrip("-")
    return f"{p}-{name}" if p else name


def _provider_environment() -> str:
    return str(config.PROVIDER_ENVIRONMENT or "datalab").strip() or "datalab"


def _provider_environment_annotations(annotation_key: str) -> dict[str, str]:
    return {annotation_key: _provider_environment()}


DEFAULT_MAX_SESSIONS = 3


def _max_sessions() -> int:
    raw = config.MAX_SESSIONS
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid MAX_SESSIONS=%r; using %s.", raw, DEFAULT_MAX_SESSIONS)
        return DEFAULT_MAX_SESSIONS

    return max(0, value)


def _workspace_name_pattern() -> str:
    p = (config.PREFIX_FOR_NAME or "").strip().rstrip("-")
    if p:
        return rf"^{re.escape(p)}-[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
    return r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat() if isinstance(ts, datetime) else str(ts)


def _to_datetime(ts: Any) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    s = str(ts).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


WORKSPACE_NAME_PATTERN = _workspace_name_pattern()
workspace_path_type = Path(..., pattern=WORKSPACE_NAME_PATTERN)

API_STORAGE = "pkg.internal/v1beta1"
API_DATALAB = "pkg.internal/v1beta2"
KIND_STORAGE = "Storage"
KIND_DATALAB = "Datalab"
CRD_STORAGE = "storages.pkg.internal"
CRD_DATALAB = "datalabs.pkg.internal"
DEFAULT_SESSION_NAME = "default"
SESSION_STATE_STARTED = SessionState.STARTED.value
SESSION_STATE_STOPPED = SessionState.STOPPED.value
STORAGE_ENVIRONMENT_ANNOTATION = "storages.pkg.internal/environment"
DATALAB_ENVIRONMENT_ANNOTATION = "datalabs.pkg.internal/environment"


@app.on_event("startup")
async def load_k8s_config() -> None:
    _configured_store_types()
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
    resource = _res_optional(api, kind)
    if resource is None:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=f"CRD for {kind} ({api}) is not installed",
        )
    return resource


def _provider_disabled(kind: str) -> bool:
    setting = {KIND_STORAGE: "DISABLE_STORAGE", KIND_DATALAB: "DISABLE_DATALAB"}.get(kind)
    return bool(setting and _as_bool(getattr(config, setting, "false")))


def _res_optional(api: str, kind: str) -> Any:
    if _provider_disabled(kind):
        return None
    try:
        return _dyn().resources.get(api_version=api, kind=kind)
    except ResourceNotFoundError:
        return None
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        raise


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


@app.get("/status", status_code=HTTPStatus.OK, tags=["System"], summary="Health and provider configuration")
async def status() -> Response:
    return JSONResponse(
        {
            "ok": True,
            "storage_enabled": not _provider_disabled(KIND_STORAGE),
            "datalab_enabled": not _provider_disabled(KIND_DATALAB),
        }
    )


def _get_cr(api_version: str, kind: str, name: str, required: bool) -> Any | None:
    api = _res_required(api_version, kind) if required else _res_optional(api_version, kind)
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


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, int | float):
        return v != 0
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "on"}


def _workspace_permissions(request: Request, workspace_name: str) -> set[UserPermission]:
    user_ctx = request.state.user

    workspace_perms = set()
    if "*" in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"]["*"]
    if workspace_name in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"][workspace_name]
    return workspace_perms


def _require_workspace_permission(request: Request, workspace_name: str, permission: UserPermission) -> None:
    if permission not in _workspace_permissions(request, workspace_name):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")


def _resource_name(obj: Any) -> str | None:
    if isinstance(obj, dict):
        metadata = obj.get("metadata") or {}
        return _clean_str(metadata.get("name")) if isinstance(metadata, dict) else None

    metadata = getattr(obj, "metadata", None)
    if isinstance(metadata, dict):
        return _clean_str(metadata.get("name"))
    return _clean_str(getattr(metadata, "name", None))


def _session_name(item: Any) -> str | None:
    if isinstance(item, dict):
        return _clean_str(item.get("name"))
    return None


def _session_state(item: Any) -> str | None:
    if isinstance(item, dict):
        state = item.get("state", SESSION_STATE_STARTED)
        if state in (SESSION_STATE_STARTED, SESSION_STATE_STOPPED):
            return state
    return None


def _session_item(name: str, state: str | SessionState) -> dict[str, str]:
    return {"name": name, "state": getattr(state, "value", state)}


def _initial_sessions_for_mode(session_mode: str) -> list[dict[str, str]]:
    match session_mode.strip().lower():
        case "on":
            return [_session_item(DEFAULT_SESSION_NAME, SESSION_STATE_STARTED)]
        case "auto":
            return [_session_item(DEFAULT_SESSION_NAME, SESSION_STATE_STOPPED)]
        case _:
            return []


def _session_declarations(spec: dict[str, Any]) -> list[Any]:
    sessions = spec.get("sessions") or []
    return sessions if isinstance(sessions, list) else []


def _find_session(sessions: Sequence[Any], session_id: str) -> Any | None:
    for session in sessions:
        if _session_name(session) == session_id:
            return session
    return None


def _session_index(sessions: Sequence[Any], session_id: str) -> int | None:
    for index, session in enumerate(sessions):
        if _session_name(session) == session_id:
            return index
    return None


def _session_state_patch(sessions: Sequence[Any], session_id: str, state: str | SessionState) -> list[dict[str, Any]]:
    index = _session_index(sessions, session_id)
    if index is None:
        return []

    return [
        {
            "op": "replace" if "state" in sessions[index] else "add",
            "path": f"/spec/sessions/{index}/state",
            "value": getattr(state, "value", state),
        }
    ]


def _datalab_status(datalab: Any) -> dict[str, Any]:
    st = getattr(datalab, "status", None)
    if st is None:
        return {}
    if isinstance(st, dict):
        return st
    if hasattr(st, "to_dict"):
        return st.to_dict()
    return {}


def _session_status_entries(datalab: Any) -> dict[str, dict[str, Any]]:
    sessions = _datalab_status(datalab).get("sessions") or []
    if isinstance(sessions, list):
        return {name: item for item in sessions if isinstance(item, dict) and (name := _session_name(item))}
    return {}


def _session_status_payload(datalab: Any, session_id: str) -> dict[str, Any]:
    return _session_status_entries(datalab).get(session_id, {})


def _session_runtime_ready(payload: dict[str, Any]) -> bool:
    return bool(_http_url(payload.get("url")) and payload.get("state") == SESSION_STATE_STARTED and payload.get("phase") == "Running")


def _sessions_from_datalab(datalab: Any, *, management: bool = False) -> list[Session]:
    items = list(_session_declarations(_to_spec_dict(datalab) or {})) if management else []
    published = _session_status_entries(datalab)
    declared_names = {_session_name(item) for item in items}
    items.extend({"name": name, "state": payload.get("state")} for name, payload in published.items() if name not in declared_names)

    sessions: list[Session] = []
    seen: set[str] = set()
    for item in items:
        name = _session_name(item)
        if not name or name in seen:
            continue
        seen.add(name)

        state_value = _session_state(item)
        if state_value is None:
            logger.warning("Skipping session '%s': invalid state.", name)
            continue
        state = SessionState(state_value)

        payload = published.get(name, {})
        url = _http_url(payload.get("url"))
        pvc_size = _parse_storage_quantity(payload.get("pvcSize"))

        try:
            sessions.append(
                Session(
                    name=name,
                    state=state,
                    url=url,
                    ready=state == SessionState.STARTED and _session_runtime_ready(payload),
                    phase=_clean_str(payload.get("phase")),
                    message=_clean_str(payload.get("message")),
                    pvc_size=_format_storage_quantity(pvc_size[1]) if pvc_size is not None else None,
                )
            )
        except ValueError as e:
            logger.warning("Skipping invalid session declaration %r: %s", item, e)

    return sessions


def _bucketname_from(d: dict) -> str | None:
    return _clean_str(d.get("bucketName"))


def _bucket_lifecycle_rules_from_provider(d: dict[str, Any]) -> list[BucketLifecycleRule]:
    raw_rules = d.get("lifecycleRules") or []
    if not isinstance(raw_rules, list):
        return []

    rules: list[BucketLifecycleRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            logger.warning("Skipping non-dict lifecycle rule: %r", raw_rule)
            continue

        target = _clean_str(raw_rule.get("target"))
        if target is None:
            logger.warning("Skipping invalid lifecycle rule %r: missing target", raw_rule)
            continue

        try:
            mode = BucketLifecycleRuleMode(_clean_str(raw_rule.get("mode")) or BucketLifecycleRuleMode.DELETE.value)
            rules.append(
                BucketLifecycleRule(
                    target=target,
                    mode=mode,
                    min_age=raw_rule.get("minAge"),
                    at=raw_rule.get("at"),
                )
            )
        except ValueError as e:
            logger.warning("Skipping invalid lifecycle rule %r: %s", raw_rule, e)

    return rules


def _bucket_lifecycle_rules_to_provider(rules: Sequence[BucketLifecycleRule]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rule in rules or []:
        mode = getattr(rule.mode, "value", rule.mode)
        item: dict[str, Any] = {
            "target": rule.target,
            "mode": mode,
        }
        if rule.min_age is not None:
            item["minAge"] = rule.min_age
        elif rule.at is not None:
            item["at"] = _iso(rule.at)
        out.append(item)
    return out


def _dedup_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _store_field_for_type(store_type: StoreType) -> str:
    return {
        StoreType.DATABASE: "databases",
        StoreType.CACHE: "cacheStores",
        StoreType.DOCUMENT: "documentStores",
    }[store_type]


def _default_storage_for_type(store_type: StoreType) -> str:
    return {
        StoreType.DATABASE: "1Gi",
        StoreType.CACHE: "1Gi",
        StoreType.DOCUMENT: "10Gi",
    }[store_type]


def _configured_store_types() -> list[StoreType]:
    supported = {
        "postgres": StoreType.DATABASE,
        "redis": StoreType.CACHE,
        "mongo": StoreType.DOCUMENT,
    }
    enabled = set()
    for raw_entry in config.STORES.split(","):
        entry = raw_entry.strip().lower()
        if not entry:
            continue
        if entry not in supported:
            message = "STORES must contain postgres, redis, or mongo."
            raise ValueError(message)
        enabled.add(supported[entry])
    return [store_type for store_type in StoreType if store_type in enabled]


def _available_store_types(datalab_installed: bool) -> list[StoreType]:
    return _configured_store_types() if datalab_installed else []


def _stores_from_map(
    spec: dict[str, Any],
    field: str,
    store_type: StoreType,
    creation_timestamp: datetime | None,
) -> list[Store]:
    stores: list[Store] = []
    items = spec.get(field) or {}
    if not isinstance(items, dict):
        return stores

    for name, cfg in items.items():
        store_name = str(name or "").strip()
        if not store_name:
            continue
        storage = None
        if isinstance(cfg, dict):
            storage = _clean_str(cfg.get("storage"))
        stores.append(
            Store(
                name=store_name,
                type=store_type,
                instance=store_name,
                storage=storage,
                backup_storage=None,
                creation_timestamp=creation_timestamp,
            )
        )
    return stores


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
    storage_api = _res_required(API_STORAGE, KIND_STORAGE)
    try:
        storages = storage_api.get(namespace=current_namespace())
    except ApiException as e:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail="Listing bucket access requests failed") from e
    storage_items = getattr(storages, "items", []) or []

    out: list[BucketAccessRequest] = []

    for obj in storage_items:
        workspace_name = (getattr(obj.metadata, "name", None) or "").strip()
        spec = _to_spec_dict(obj)
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
        spec = _to_spec_dict(obj)
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
        spec = _to_spec_dict(obj)
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

                granted_at = g.get("grantedAt")
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


def _clean_str(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return None


def _http_url(value: object) -> str | None:
    url = _clean_str(value)
    if url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
                return url
        except ValueError:
            return None
    return None


def _matches_connection_selector(connection: CredentialReference, selectors: Sequence[str]) -> bool:
    return any(
        selector in {"*", "*:*", f"{connection.type}:{connection.name}", f"{connection.type}:*", f"*:{connection.name}"}
        for selector in selectors
    )


def _oauth2_from_datalab(datalab: Any, workspace_name: str, *, resolve: Sequence[str]) -> list[OAuth2Connection]:
    connections = []
    for entry in _datalab_status(datalab).get("oauth2") or []:
        if not isinstance(entry, dict):
            continue
        try:
            connection = OAuth2Connection.model_validate(
                {
                    **{key: entry[key] for key in ("name", "type", "ready") if key in entry},
                    "issuer_url": entry.get("issuerUrl"),
                    "secret_ref": entry.get("secretRef"),
                }
            )
        except ValidationError:
            logger.warning("Ignoring invalid OAuth2 metadata for workspace '%s'.", workspace_name)
            continue
        if _matches_connection_selector(connection, resolve):
            _resolve_connection(connection)
        connections.append(connection)
    return connections


def _connections_from_datalab(
    datalab: Any, workspace_name: str, *, resolve: Sequence[str], oauth2_refs: set[tuple[str, str]]
) -> list[Connection]:
    entries = _datalab_status(datalab).get("connections") or []
    connections = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            connection = Connection.model_validate(
                {
                    **{
                        key: entry[key]
                        for key in ("name", "type", "ready", "endpoint", "region", "instance", "group", "role")
                        if key in entry
                    },
                    "secret_ref": entry.get("secretRef"),
                    "target_namespace": entry.get("targetNamespace"),
                }
            )
        except ValidationError:
            logger.warning("Ignoring invalid connection metadata for workspace '%s'.", workspace_name)
            continue
        if _matches_connection_selector(connection, resolve):
            if (connection.secret_ref.namespace, connection.secret_ref.name) in oauth2_refs:
                connection.resolution_error = "oauth2_reference"
            else:
                _resolve_connection(connection)
        connections.append(connection)
    return connections


def _resolve_connection(connection: CredentialReference) -> None:
    ref = connection.secret_ref
    if not connection.ready:
        connection.resolution_error = "not_ready"
        return
    try:
        secret = fetch_secret(ref.name, ref.namespace)
    except Exception:
        logger.warning("Could not read connection Secret %s/%s.", ref.namespace, ref.name)
        connection.resolution_error = "secret_unavailable"
        return
    if secret is None or not secret.data:
        connection.resolution_error = "secret_not_found"
        return
    try:
        connection.credentials = {key: base64.b64decode(value, validate=True).decode("utf-8") for key, value in secret.data.items()}
    except (ValueError, TypeError, UnicodeDecodeError):
        connection.resolution_error = "invalid_secret"


_BINARY_STORAGE_UNITS = (
    ("Ei", 1024**6),
    ("Pi", 1024**5),
    ("Ti", 1024**4),
    ("Gi", 1024**3),
    ("Mi", 1024**2),
    ("Ki", 1024),
)


def _parse_storage_quantity(raw: Any) -> tuple[str, Decimal] | None:
    value = _clean_str(raw)
    if value is None:
        return None
    try:
        parsed = parse_quantity(value)
    except ValueError:
        logger.warning("Ignoring invalid Kubernetes storage quantity %r.", value)
        return None
    if not parsed.is_finite() or parsed < 0:
        logger.warning("Ignoring invalid Kubernetes storage quantity %r.", value)
        return None
    return value, parsed


def _format_storage_quantity(value: Decimal) -> str:
    if value == 0:
        return "0"

    for suffix, factor in _BINARY_STORAGE_UNITS:
        quantity = value / factor
        if quantity == quantity.to_integral_value():
            return f"{int(quantity)}{suffix}"

    return format(value.normalize(), "f")


def _declared_stores(
    datalab_spec: dict[str, Any], available_store_types: Sequence[StoreType], dl_created_at: datetime | None
) -> list[Store]:
    stores: list[Store] = []

    db_hosts = (datalab_spec or {}).get("databases") or {}

    if not isinstance(db_hosts, dict):
        db_hosts = {}

    seen_db: set[tuple[str, str]] = set()

    if StoreType.DATABASE in available_store_types:
        for host, host_cfg in db_hosts.items():
            if not isinstance(host_cfg, dict):
                continue
            names = host_cfg.get("names") or []
            if not isinstance(names, list):
                continue
            for n in names:
                name = str(n or "").strip()
                if not name or (host, name) in seen_db:
                    continue
                seen_db.add((host, name))
                stores.append(
                    Store(
                        name=name,
                        type=StoreType.DATABASE,
                        instance=host,
                        storage=_clean_str(host_cfg.get("storage")),
                        backup_storage=_clean_str(host_cfg.get("backupStorage")),
                        creation_timestamp=dl_created_at,
                    )
                )

    if StoreType.CACHE in available_store_types:
        stores.extend(_stores_from_map(datalab_spec, "cacheStores", StoreType.CACHE, dl_created_at))
    if StoreType.DOCUMENT in available_store_types:
        stores.extend(_stores_from_map(datalab_spec, "documentStores", StoreType.DOCUMENT, dl_created_at))

    return stores


def _combine_workspace(
    request: Request,
    workspace_name: str,
    *,
    resolve_connections: Sequence[str] = ("s3:primary",),
    resolve_oauth2: Sequence[str] = (),
    management: bool = False,
) -> Workspace:
    storage_cr = _get_cr(API_STORAGE, KIND_STORAGE, workspace_name, required=False)
    datalab_cr = _get_cr(API_DATALAB, KIND_DATALAB, workspace_name, required=False)
    if storage_cr is None and datalab_cr is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Workspace not found")

    user_ctx = request.state.user
    workspace_perms = _workspace_permissions(request, workspace_name)
    available_store_types = _available_store_types(datalab_cr is not None)

    storage_spec = _to_spec_dict(storage_cr) or {}
    datalab_spec = _to_spec_dict(datalab_cr) or {}

    principal = storage_spec.get("principal") or workspace_name

    buckets = storage_spec.get("buckets") or []
    all_buckets: list[str] = []
    discoverable_buckets: list[str] = []
    bucket_lifecycle_rules: dict[str, list[BucketLifecycleRule]] = {}

    for it in buckets:
        bname = _bucketname_from(it or {}) or ""
        if not bname:
            continue
        all_buckets.append(bname)
        if isinstance(it, dict):
            bucket_lifecycle_rules[bname] = _bucket_lifecycle_rules_from_provider(it)
        if _as_bool((it or {}).get("discoverable")):
            discoverable_buckets.append(bname)

    relevant_bucket_access_requests = (
        _extract_relevant_bucket_access_requests(_dedup_preserve(discoverable_buckets), principal, workspace_name)
        if storage_cr is not None and UserPermission.VIEW_BUCKETS in workspace_perms
        else []
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
                creation_timestamp=_to_datetime(ts),
            )
        )

    sessions = _sessions_from_datalab(datalab_cr, management=management) if datalab_cr is not None else []

    oauth2 = _oauth2_from_datalab(datalab_cr, workspace_name, resolve=resolve_oauth2)
    connections = _connections_from_datalab(
        datalab_cr,
        workspace_name,
        resolve=resolve_connections,
        oauth2_refs={(connection.secret_ref.namespace, connection.secret_ref.name) for connection in oauth2},
    )
    credentials: Credentials | None = None
    primary = next((connection for connection in connections if connection.type == "s3" and connection.name == "primary"), None)
    if primary and primary.credentials and primary.endpoint and primary.region and all_buckets:
        access = _clean_str(primary.credentials.get("AWS_ACCESS_KEY_ID"))
        secret_key = _clean_str(primary.credentials.get("AWS_SECRET_ACCESS_KEY"))
        if access and secret_key:
            credentials = Credentials(
                bucketname=all_buckets[0],
                access=access,
                secret=secret_key,
                endpoint=primary.endpoint,
                region=primary.region,
            )

    metadata = getattr(storage_cr if storage_cr is not None else datalab_cr, "metadata", None)
    creation_timestamp = getattr(metadata, "creationTimestamp", None)
    version = getattr(metadata, "resourceVersion", None)
    resources = [resource for resource in (storage_cr, datalab_cr) if resource is not None]
    ready = all(_resource_ready(resource) for resource in resources) and all(connection.ready for connection in [*connections, *oauth2])
    workspace_status = WorkspaceStatus.READY if ready else WorkspaceStatus.PROVISIONING

    storage = Storage(
        available=storage_cr is not None,
        buckets=[
            Bucket(
                name=b,
                discoverable=b in discoverable_buckets,
                lifecycle_rules=bucket_lifecycle_rules.get(b, []),
                creation_timestamp=None,
            )
            for b in all_buckets
        ],
        credentials=credentials if storage_cr is not None else None,
        bucket_access_requests=relevant_bucket_access_requests,
    )
    datalab = Datalab(
        memberships=memberships,
        available=datalab_cr is not None,
        available_store_types=available_store_types,
        stores=_declared_stores(datalab_spec, available_store_types, dl_created_at) if management else _published_stores(connections),
        vclusters=_vclusters_from_datalab(datalab_cr, management=management),
        sessions=sessions,
        max_sessions=_max_sessions(),
        connections=connections,
        oauth2=oauth2,
    )

    if UserPermission.VIEW_CONNECTION_CREDENTIALS not in workspace_perms:
        storage.credentials = None
    if UserPermission.VIEW_BUCKETS not in workspace_perms:
        storage.buckets = []
        storage.bucket_access_requests = []
    if UserPermission.VIEW_MEMBERS not in workspace_perms:
        datalab.memberships = []
    if UserPermission.VIEW_STORES not in workspace_perms:
        datalab.stores = []
    if UserPermission.VIEW_VCLUSTERS not in workspace_perms:
        datalab.vclusters = []
    if UserPermission.VIEW_SESSIONS not in workspace_perms:
        datalab.sessions = []

    workspace = Workspace(
        name=workspace_name,
        creation_timestamp=creation_timestamp,
        version=version,
        status=workspace_status,
        storage=storage,
        datalab=datalab,
        user=UserContext(
            name=user_ctx["username"],
            permissions=sorted(workspace_perms),
        ),
    )

    logger.info("Returning workspace '%s' for user '%s'", workspace_name, user_ctx["username"])

    if config.AUTH_DEBUG:
        logger.debug(f"workspace={workspace}")

    return workspace


@app.post(
    "/workspaces",
    status_code=HTTPStatus.CREATED,
    tags=["Workspaces"],
    summary="Create a new workspace",
    description=(
        "Creates a workspace with the installed Storage and Datalab providers. "
        "Datalab sessions are created based on the configured session mode."
    ),
    responses={
        201: {"description": "Workspace created."},
        422: {"description": "Workspace with this name already exists or invalid input."},
        502: {"description": "Backend error while creating cluster resources."},
    },
)
async def create_workspace(data: WorkspaceCreate) -> dict[str, str]:
    workspace_name = _with_prefix(data.preferred_name or uuid.uuid4().hex[:12])
    try:
        validate_resource_name(workspace_name)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(e)) from e

    storage_api = _res_optional(API_STORAGE, KIND_STORAGE)
    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    if storage_api is None and datalab_api is None:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail="No workspace provider is installed")

    for api in (storage_api, datalab_api):
        if api is None:
            continue
        try:
            api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                continue
            raise
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "Workspace with this name already exists"},
        )

    if storage_api is not None:
        try:
            storage_api.create(
                {
                    "apiVersion": API_STORAGE,
                    "kind": KIND_STORAGE,
                    "metadata": {
                        "name": workspace_name,
                        "annotations": _provider_environment_annotations(STORAGE_ENVIRONMENT_ANNOTATION),
                    },
                    "spec": {
                        "principal": workspace_name,
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
        session_mode = str(config.SESSION_MODE).strip().lower()
        sessions = _initial_sessions_for_mode(session_mode)[: _max_sessions()]
        datalab_spec: dict[str, Any] = {
            "users": [slugify(data.default_owner, max_length=32) or str(uuid.uuid4())],
        }
        if _as_bool(config.USE_VCLUSTER):
            datalab_spec["vclusters"] = {"vc0": {}}
        if sessions:
            datalab_spec["sessions"] = sessions

        try:
            datalab_api.create(
                {
                    "apiVersion": API_DATALAB,
                    "kind": KIND_DATALAB,
                    "metadata": {
                        "name": workspace_name,
                        "annotations": _provider_environment_annotations(DATALAB_ENVIRONMENT_ANNOTATION),
                    },
                    "spec": datalab_spec,
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


def _broker_timeout_seconds() -> float:
    raw = config.TOKEN_BROKER_TIMEOUT_SECONDS
    try:
        return max(1.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        logger.warning("Invalid TOKEN_BROKER_TIMEOUT_SECONDS=%r; using 10 seconds.", raw)
        return 10.0


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        _header_b64, payload_b64, _sig = token.split(".")
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _payload_has_audience(payload: dict[str, Any], expected_audience: str) -> bool:
    aud = payload.get("aud")
    if isinstance(aud, str):
        return aud == expected_audience
    if isinstance(aud, list):
        return expected_audience in aud
    return False


def _workspace_oauth_client(workspace_name: str, datalab: Any) -> OAuth2Connection:
    if datalab is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Workspace not found")
    clients = [
        client
        for client in _oauth2_from_datalab(datalab, workspace_name, resolve=())
        if client.type == "client" and client.name == workspace_name
    ]
    if not clients:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": "workspace_oauth_client_not_found"})
    if len(clients) != 1:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "workspace_oauth_client_ambiguous"})
    client = clients[0]
    if not client.ready:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail={"error": "workspace_oauth_client_not_ready"})
    return client


def _workspace_oauth_client_credentials(client: OAuth2Connection) -> tuple[str, str]:
    secret_name = client.secret_ref.name
    secret = fetch_secret(secret_name, client.secret_ref.namespace)
    if not secret or not getattr(secret, "data", None):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={"error": "oauth_client_secret_not_found", "secret": secret_name},
        )

    try:
        client_secret = base64.b64decode(secret.data["clientSecret"], validate=True).decode("utf-8").strip()
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "oauth_client_secret_invalid", "secret": secret_name},
        ) from e

    if not client_secret:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "oauth_client_secret_invalid", "secret": secret_name},
        )
    return client.name, client_secret


def _require_workspace_token_broker_role(request: Request, workspace_name: str) -> None:
    user_ctx = request.state.user
    can_issue_tokens = UserPermission.ISSUE_TOKENS in _workspace_permissions(request, workspace_name)
    if not user_ctx.get("is_admin", False) and not can_issue_tokens:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")


def _discover_oauth_metadata(issuer: str) -> dict[str, Any]:
    issuer_url = _http_url(issuer)
    if not issuer_url or urlsplit(issuer_url).scheme != "https" or urlsplit(issuer_url).query or urlsplit(issuer_url).fragment:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "oauth_issuer_invalid"},
        )
    try:
        response = requests.get(
            f"{issuer_url.rstrip('/')}/.well-known/openid-configuration",
            headers={"Accept": "application/json"},
            timeout=_broker_timeout_seconds(),
            allow_redirects=False,
        )
        response.raise_for_status()
        metadata = response.json() if response.status_code == HTTPStatus.OK else None
    except requests.RequestException as e:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_discovery_failed"}) from e
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_discovery_invalid"}) from e
    if not isinstance(metadata, dict) or metadata.get("issuer") != issuer_url:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_discovery_invalid"})
    token_endpoint = _http_url(metadata.get("token_endpoint"))
    if not token_endpoint or urlsplit(token_endpoint).scheme != "https" or urlsplit(token_endpoint).fragment:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_discovery_invalid"})
    return metadata


def _request_workspace_token(
    token_endpoint: str, client_id: str, client_secret: str, data: Mapping[str, str | list[str]]
) -> dict[str, Any]:
    try:
        response = requests.post(
            token_endpoint,
            data=data,
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=_broker_timeout_seconds(),
            allow_redirects=False,
        )
    except requests.RequestException as e:
        logger.warning("Workspace token request failed: %s", e)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_endpoint_unreachable"},
        ) from e

    if not response.ok:
        logger.warning("Workspace token endpoint returned status %s.", response.status_code)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_endpoint_error", "status": response.status_code},
        )

    try:
        payload = response.json()
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_endpoint_invalid_json"},
        ) from e

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_endpoint_invalid_json"},
        )

    return payload


def _workspace_exchange_scopes(datalab: Any, workspace_name: str, scope: str) -> dict[str, str]:
    instances = (_to_spec_dict(datalab) or {}).get("vclusters") or {}
    allowed = {}
    declared = {}
    for instance, settings in instances.items():
        for group in settings.get("groups") or []:
            name = group.get("name")
            if name and name != "cluster-admin":
                profile_scope = f"{workspace_name}:vclusters_{instance}_{name}"
                allowed[profile_scope] = f"vcluster_{instance}_{name}"
                declared[profile_scope] = group
    requested = sorted(set(scope.split()))
    if not requested or any(name not in allowed for name in requested):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_scope", "message": "Request only configured additional vcluster profile scopes"},
        )
    published = {
        f"{workspace_name}:vclusters_{entry.get('instance')}_{entry.get('group')}": entry
        for entry in _datalab_status(datalab).get("connections") or []
        if isinstance(entry, dict) and entry.get("type") == "vcluster"
    }
    for name in requested:
        entry = published.get(name, {})
        group = declared[name]
        if (
            entry.get("ready") is not True
            or entry.get("targetNamespace") != group.get("namespace")
            or entry.get("role") != group.get("role")
        ):
            raise HTTPException(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                detail={"error": "vcluster_profile_not_ready", "scope": name},
            )
    return {name: allowed[name] for name in requested}


def _workspace_exchange_subject(request: Request, client: OAuth2Connection, roles: set[str]) -> str:
    claims = getattr(request.state, "token_claims", {})
    resource_access = claims.get("resource_access") or {}
    workspace_access = resource_access.get(client.name, {}) if isinstance(resource_access, dict) else {}
    caller_roles = workspace_access.get("roles", []) if isinstance(workspace_access, dict) else []
    subject = claims.get("sub")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or claims.get("iss") != client.issuer_url
        or not (_payload_has_audience(claims, client.name) or claims.get("azp") == client.name)
        or not isinstance(caller_roles, list)
        or any(not isinstance(role, str) for role in caller_roles)
        or not roles.issubset(caller_roles)
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail={
                "error": "exchange_not_permitted",
                "message": "Caller must hold the requested workspace roles and a matching user token",
            },
        )
    return subject


def _workspace_signing_keys(metadata: Mapping[str, Any]) -> dict[str, Any]:
    uri = _http_url(metadata.get("jwks_uri"))
    if not uri or urlsplit(uri).scheme != "https" or urlsplit(uri).fragment:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_jwks_uri_invalid"})
    try:
        response = requests.get(uri, timeout=_broker_timeout_seconds(), allow_redirects=False, headers={"Accept": "application/json"})
        response.raise_for_status()
        keys = response.json() if response.status_code == HTTPStatus.OK else None
    except (requests.RequestException, ValueError) as e:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_jwks_failed"}) from e
    if not isinstance(keys, dict) or not isinstance(keys.get("keys"), list) or not keys["keys"]:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "oauth_jwks_invalid"})
    return keys


def _token_has_only_workspace_roles(payload: Mapping[str, Any], workspace_name: str, expected: set[str]) -> bool:
    resources = payload.get("resource_access")
    if not isinstance(resources, dict) or workspace_name not in resources:
        return False
    for name, access in resources.items():
        roles = access.get("roles") if isinstance(access, dict) else None
        if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
            return False
        if set(roles) != (expected if name == workspace_name else set()):
            return False
    realm = payload.get("realm_access", {})
    authorization = payload.get("authorization", {})
    return isinstance(realm, dict) and not realm.get("roles") and isinstance(authorization, dict) and not authorization.get("permissions")


def _validate_exchanged_workspace_token(
    token: WorkspaceToken, client: OAuth2Connection, keys: dict[str, Any], subject: str, scopes: Mapping[str, str]
) -> None:
    invalid_token = HTTPException(
        status_code=HTTPStatus.BAD_GATEWAY,
        detail={
            "error": "token_validation_failed",
            "message": "Exchanged access token does not match the requested identity and permissions",
        },
    )
    verifier = JsonWebToken(["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"])
    try:
        claims = verifier.decode(
            token.access_token,
            keys,
            claims_options={
                "iss": {"essential": True, "value": client.issuer_url},
                "sub": {"essential": True, "value": subject},
                "aud": {"essential": True},
                "exp": {"essential": True},
            },
        )
        claims.validate()
    except (JoseError, ValueError, TypeError, KeyError) as e:
        raise invalid_token from e
    audiences = claims["aud"]
    if isinstance(audiences, str):
        audiences = [audiences]
    allowed_scopes = set(scopes) | {"openid", "basic", "profile", "email"}
    if (
        not isinstance(audiences, list)
        or any(not isinstance(audience, str) for audience in audiences)
        or set(audiences) != {config.AUTH_AUDIENCE, client.name}
        or not _token_has_only_workspace_roles(claims, client.name, {"ws_api", *scopes.values()})
        or any(
            not isinstance(value, str) or not set(scopes).issubset(value.split()) or not set(value.split()).issubset(allowed_scopes)
            for value in (claims.get("scope"), token.scope)
        )
    ):
        raise invalid_token


def _validate_brokered_workspace_token(token_response: Mapping[str, Any], workspace_name: str) -> WorkspaceToken:
    access_token = _clean_str(token_response.get("access_token"))
    if not access_token:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_endpoint_missing_access_token"},
        )

    payload = _decode_jwt_payload(access_token)
    expected_audience = config.AUTH_AUDIENCE
    if payload is None or not _payload_has_audience(payload, expected_audience):
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_validation_failed", "message": "access token is not audience-restricted for Workspace API"},
        )

    resource_access = payload.get("resource_access") or {}
    workspace_access = resource_access.get(workspace_name) if isinstance(resource_access, dict) else None
    roles = workspace_access.get("roles") if isinstance(workspace_access, dict) else []
    if not isinstance(roles, list) or "ws_api" not in roles:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_validation_failed", "message": "access token is missing the workspace ws_api role"},
        )

    token_type = _clean_str(token_response.get("token_type"))
    if not token_type or token_type.lower() != "bearer":
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": "token_validation_failed", "message": "access token response is not a bearer token"},
        )

    token = WorkspaceToken(
        access_token=access_token,
        token_type=token_type,
        expires_in=token_response.get("expires_in"),
        scope=token_response.get("scope"),
    )

    return token


@app.get(
    "/workspaces/{workspace_name}/token",
    status_code=HTTPStatus.OK,
    response_model=WorkspaceToken,
    tags=["Workspaces"],
    summary="Broker a workspace OAuth access token",
    description=(
        "Admin-only token endpoint. Omit scope for a workspace service-account token. "
        "Supply configured profile scopes to exchange the caller's token for restricted workspace and vcluster access."
    ),
    responses={
        200: {"description": "Workspace access token returned."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace, published OAuth2 client, or referenced Secret not found."},
        422: {"description": "Invalid or unconfigured profile scope."},
        502: {"description": "Authorization server or token validation failure."},
        503: {"description": "Datalab provider unavailable or the OAuth2 client is not ready."},
    },
)
async def get_workspace_token(
    request: Request,
    workspace_name: str = workspace_path_type,
    scope: Annotated[
        str | None, Query(max_length=2048, description="Space-separated workspace-qualified additional vcluster profile scopes.")
    ] = None,
) -> Response:
    _require_workspace_token_broker_role(request, workspace_name)
    datalab = _get_cr(API_DATALAB, KIND_DATALAB, workspace_name, required=True)
    client = _workspace_oauth_client(workspace_name, datalab)
    scopes = _workspace_exchange_scopes(datalab, workspace_name, scope) if scope is not None else {}
    subject = _workspace_exchange_subject(request, client, {"ws_api", *scopes.values()}) if scopes else None
    metadata = _discover_oauth_metadata(client.issuer_url)
    keys = _workspace_signing_keys(metadata) if scopes else {}
    client_id, client_secret = _workspace_oauth_client_credentials(client)
    data: dict[str, str | list[str]] = {"grant_type": "client_credentials", "audience": config.AUTH_AUDIENCE}
    if scopes:
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": request.state.access_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": " ".join(scopes),
            "audience": sorted({config.AUTH_AUDIENCE, workspace_name}),
        }
    token_response = _request_workspace_token(metadata["token_endpoint"], client_id, client_secret, data)
    token = _validate_brokered_workspace_token(token_response, workspace_name)
    if subject is not None:
        _validate_exchanged_workspace_token(token, client, keys, subject, scopes)
    elif not _token_has_only_workspace_roles(_decode_jwt_payload(token.access_token) or {}, workspace_name, {"ws_api"}):
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail={"error": "token_validation_failed"})
    return JSONResponse(
        token.model_dump(mode="json"),
        status_code=HTTPStatus.OK,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


@app.get(
    "/workspaces",
    status_code=HTTPStatus.OK,
    response_model=list[WorkspaceListItem],
    tags=["Workspaces"],
    summary="List workspaces",
    description="Returns actual workspace names visible to the authenticated caller.",
    responses={
        200: {"description": "Visible workspace names returned."},
        502: {"description": "Backend failure while listing workspaces."},
    },
)
async def list_workspaces(request: Request) -> Response:
    workspace_names: set[str] = set()
    datalabs_by_name: dict[str, Any] = {}
    for api_version, kind in ((API_STORAGE, KIND_STORAGE), (API_DATALAB, KIND_DATALAB)):
        api = _res_optional(api_version, kind)
        if api is None:
            continue
        try:
            resources = api.get(namespace=current_namespace())
        except ApiException as e:
            raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail="Listing workspaces failed") from e
        for item in getattr(resources, "items", []) or []:
            name = _resource_name(item)
            if name and _workspace_permissions(request, name):
                workspace_names.add(name)
                if kind == KIND_DATALAB:
                    datalabs_by_name[name] = item

    workspaces = [
        WorkspaceListItem(
            name=name,
            url=make_external_url(request, f"/workspaces/{name}"),
            sessions=[
                WorkspaceListSession(
                    name=session.name,
                    url=session.url,
                )
                for session in _sessions_from_datalab(datalabs_by_name[name])
                if UserPermission.VIEW_SESSIONS in _workspace_permissions(request, name) and session.ready and session.url
            ]
            if name in datalabs_by_name
            else [],
        )
        for name in sorted(workspace_names)
    ]

    accept_header = request.headers.get("accept", "").lower()
    if "text/html" in accept_header:
        open_icon = (
            "<svg class='open-icon' viewBox='0 0 24 24' aria-hidden='true' focusable='false'>"
            "<path d='M14 3h7v7h-2V6.41l-9.83 9.83-1.41-1.41L17.59 5H14V3z'/>"
            "<path d='M5 5h7v2H7v12h12v-5h2v7H5V5z'/>"
            "</svg>"
        )
        rows = "".join(
            "<li>"
            f"<a class='workspace-link' href='{html.escape(workspace.url, quote=True)}"
            "?resolve_connections=*"
            + ("&amp;resolve_oauth2=*" if UserPermission.VIEW_OAUTH2_CREDENTIALS in _workspace_permissions(request, workspace.name) else "")
            + "'>"
            f"<span>{html.escape(workspace.name)}</span>{open_icon}"
            "</a>"
            + (
                "<ul class='sessions'>"
                + "".join(
                    "<li>"
                    f"<a href='{html.escape(session.url, quote=True)}'>"
                    f"<span>Datalab ({html.escape(session.name)})</span>{open_icon}"
                    "</a>"
                    "</li>"
                    for session in workspace.sessions
                )
                + "</ul>"
                if workspace.sessions
                else ""
            )
            + "</li>"
            for workspace in workspaces
        )
        if not rows:
            rows = "<li class='empty'>No workspaces available.</li>"

        document = (
            "<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Workspaces</title>"
            "<style>"
            "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;"
            "background:#f7f7f5;color:#202124;}"
            "main{max-width:760px;margin:0 auto;padding:48px 24px;}"
            "h1{font-size:28px;line-height:1.2;margin:0 0 24px;}"
            "ul.workspaces{list-style:none;margin:0;padding:0;border:1px solid #d7d9d6;border-radius:8px;background:#fff;overflow:hidden;}"
            "ul.workspaces>li+li{border-top:1px solid #e6e8e5;}"
            "a{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 18px;"
            "color:#174ea6;text-decoration:none;font-weight:500;}"
            "a:hover{background:#f1f5fb;text-decoration:underline;}"
            ".workspace-link{color:#174ea6;}"
            ".sessions{list-style:none;margin:0 0 8px 28px;padding:0 16px 0 0;}"
            ".sessions a{padding:8px 18px;color:#3c4043;font-size:14px;font-weight:450;}"
            ".open-icon{width:20px;height:20px;flex:0 0 20px;fill:currentColor;}"
            ".empty{padding:16px 18px;color:#5f6368;}"
            "</style><main><h1>Workspaces</h1><ul class='workspaces'>"
            f"{rows}"
            "</ul></main></html>"
        )
        return HTMLResponse(document, headers={"Cache-Control": "no-store"})

    return JSONResponse([workspace.model_dump(mode="json") for workspace in workspaces], status_code=HTTPStatus.OK)


@app.get(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.OK,
    response_model=Workspace,
    response_model_exclude_none=True,
    tags=["Workspaces"],
    summary="Get a workspace",
    description=(
        "Returns workspace storage, memberships, "
        "status, and connection metadata. Repeat `resolve_connections=type:name` to select credentials. "
        "The default is `s3:primary`. `*` and `*:*` select all connections. Unmatched values resolve nothing. "
        "Repeat `resolve_oauth2=type:name` to select OAuth2 credentials, for example `client:ws-alice` or `client:*`. "
        "OAuth2 resolution is disabled by default and requires ws_access or ws_admin permissions. "
        "Connection selectors never resolve OAuth2 entries. Only ready entries are resolved. "
        "If `Accept: text/html` and UI mode is enabled, "
        "returns an HTML page embedding the workspace data."
    ),
    responses={
        200: {"description": "Workspace details returned."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace not found."},
    },
)
async def get_workspace(
    request: Request,
    workspace_name: str = workspace_path_type,
    view: Annotated[
        Literal["status", "management"], Query(description="Published status, or declarations for management forms.")
    ] = "status",
    resolve_connections: Annotated[
        list[str] | None,
        Query(description="Repeat type:name selectors. Default: s3:primary. * and *:* select all. Unmatched values resolve nothing."),
    ] = None,
    resolve_oauth2: Annotated[
        list[str] | None,
        Query(description="Repeat type:name selectors, such as client:ws-alice or client:*. * and *:* select all. Disabled by default."),
    ] = None,
) -> Response:
    if not _workspace_permissions(request, workspace_name):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")

    selectors = resolve_connections if resolve_connections is not None else ["s3:primary"]
    if selectors:
        _require_workspace_permission(request, workspace_name, UserPermission.VIEW_CONNECTION_CREDENTIALS)
    if resolve_oauth2:
        _require_workspace_permission(request, workspace_name, UserPermission.VIEW_OAUTH2_CREDENTIALS)
    ws = _combine_workspace(
        request, workspace_name, resolve_connections=selectors, resolve_oauth2=resolve_oauth2 or (), management=view == "management"
    )

    accept_header = request.headers.get("accept", "").lower()
    if "text/html" in accept_header and templates is not None and (config.UI_MODE == "ui" or request.query_params.get("devmode") == "true"):
        workspace_data = _to_b64_json(ws.model_dump(mode="json", exclude_none=True))

        endpoints = []
        for session in ws.datalab.sessions:
            if not session.ready or not session.url:
                continue
            endpoints.append({"id": f"Datalab ({session.name})", "url": session.url})

        endpoints_data = _to_b64_json(endpoints)

        return templates.TemplateResponse(
            "ui.html",
            {
                "request": request,
                "base_path": request.url.path,
                "workspace_data": workspace_data,
                "endpoints_data": endpoints_data,
                "frontend_url": config.FRONTEND_URL,
            },
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        ws.model_dump(mode="json", exclude_none=True),
        status_code=HTTPStatus.OK,
        headers={"Cache-Control": "no-store"},
    )


def _patch_workspace_storage(storage_api: Any, storage_obj: Any, workspace_name: str, update: WorkspaceEdit) -> None:
    storage_spec = _to_spec_dict(storage_obj) or {}

    buckets = storage_spec.get("buckets") or []
    if not isinstance(buckets, list):
        buckets = []
    existing_names = {(_bucketname_from(b) or ""): b for b in buckets if isinstance(b, dict)}

    for b in update.add_buckets or []:
        bname = (getattr(b, "name", None) or "").strip()
        if not bname:
            continue
        lifecycle_rules_was_set = "lifecycle_rules" in getattr(b, "model_fields_set", set())
        lifecycle_rules = _bucket_lifecycle_rules_to_provider(b.lifecycle_rules) if lifecycle_rules_was_set else None
        if bname not in existing_names:
            bucket_spec: dict[str, Any] = {
                "bucketName": bname,
                "discoverable": bool(getattr(b, "discoverable", False)),
            }
            if lifecycle_rules is not None:
                bucket_spec["lifecycleRules"] = lifecycle_rules

            buckets.append(bucket_spec)
            existing_names[bname] = buckets[-1]
        else:
            existing = existing_names[bname]
            if isinstance(existing, dict) and "discoverable" not in existing:
                existing["discoverable"] = bool(getattr(b, "discoverable", False))
            if isinstance(existing, dict) and lifecycle_rules is not None:
                existing["lifecycleRules"] = lifecycle_rules

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


@app.put(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.ACCEPTED,
    tags=["Workspaces"],
    summary="Update a workspace",
    description=(
        "Updates buckets and access requests on Storage, or members and stores on Datalab. Each change needs only its target resource."
    ),
    responses={
        202: {"description": "Update accepted and applied."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace not found."},
        502: {"description": "Backend error while patching cluster resources."},
    },
)
async def update_workspace(request: Request, workspace_name: str, update: WorkspaceEdit) -> dict[str, str]:
    workspace_perms = _workspace_permissions(request, workspace_name)
    if not workspace_perms:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")

    required_perms: set[UserPermission] = set()

    if update.add_buckets or update.patch_bucket_access_requests:
        required_perms.add(UserPermission.MANAGE_BUCKETS)

    if update.add_memberships:
        required_perms.add(UserPermission.MANAGE_MEMBERS)

    if update.add_stores:
        required_perms.add(UserPermission.MANAGE_STORES)

    missing = required_perms - workspace_perms
    if missing:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")

    storage_api = None
    storage_obj = None
    if update.add_buckets or update.patch_bucket_access_requests:
        storage_api = _res_required(API_STORAGE, KIND_STORAGE)

        try:
            storage_obj = storage_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
            raise

    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB) if update.add_memberships or update.add_stores else None
    available_store_types = _available_store_types(datalab_api is not None) if update.add_stores else []

    add_memberships = update.add_memberships or []
    add_stores = list(update.add_stores or [])

    if (add_memberships or add_stores) and datalab_api is None:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={
                "error": "provider_datalab_not_installed",
                "message": "Datalab CRD not present; cannot update memberships or stores.",
            },
        )

    disabled_store_types = sorted({store.type.value for store in add_stores if store.type not in available_store_types})
    if disabled_store_types:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "error": "store_type_unavailable",
                "store_types": disabled_store_types,
            },
        )

    if datalab_api is not None and (add_memberships or add_stores):
        try:
            datalab_obj = datalab_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Datalab resource not found") from e
            raise

        datalab_spec = _to_spec_dict(datalab_obj) or {}

        datalab_patch_spec: dict[str, Any] = {}

        if add_memberships:
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

            datalab_patch_spec["users"] = users
            datalab_patch_spec["userOverrides"] = user_overrides

        database_stores = [store for store in add_stores if store.type == StoreType.DATABASE]
        if database_stores:
            databases_spec = datalab_spec.get("databases")
            if not isinstance(databases_spec, dict):
                databases_spec = {}

            host_keys = [k for k in databases_spec if isinstance(k, str) and k.strip()]
            host = host_keys[0] if host_keys else "pg0"

            host_obj = databases_spec.get(host)
            if not isinstance(host_obj, dict):
                host_obj = {}

            names = host_obj.get("names")
            if not isinstance(names, list):
                names = []

            existing_database_names = {n.strip() for n in names if isinstance(n, str) and n.strip()}

            for store in database_stores:
                dn = (getattr(store, "name", None) or "").strip()
                if not dn or dn in existing_database_names:
                    continue
                names.append(dn)
                existing_database_names.add(dn)

            host_obj["names"] = names

            if "storage" not in host_obj:
                host_obj["storage"] = next((s.storage for s in database_stores if s.storage), None) or "1Gi"

            if "backupStorage" not in host_obj:
                host_obj["backupStorage"] = next((s.backup_storage for s in database_stores if s.backup_storage), None) or "10Gi"

            databases_spec[host] = host_obj
            datalab_patch_spec["databases"] = databases_spec

        for store_type in (StoreType.CACHE, StoreType.DOCUMENT):
            typed_stores = [store for store in add_stores if store.type == store_type]
            if not typed_stores:
                continue

            field = _store_field_for_type(store_type)
            stores_spec = datalab_spec.get(field)
            if not isinstance(stores_spec, dict):
                stores_spec = {}

            for store in typed_stores:
                name = (store.name or "").strip()
                if not name:
                    continue
                item = stores_spec.get(name)
                if not isinstance(item, dict):
                    item = {}
                item.setdefault("storage", store.storage or _default_storage_for_type(store_type))
                stores_spec[name] = item

            datalab_patch_spec[field] = stores_spec

        if datalab_patch_spec:
            try:
                datalab_api.patch(
                    name=workspace_name,
                    namespace=current_namespace(),
                    body={"spec": datalab_patch_spec},
                    content_type="application/merge-patch+json",
                )
            except ApiException as e:
                logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
                raise
            except Exception as e:
                logger.warning("Patching Datalab '%s' failed: %s", workspace_name, e)
                raise

    if storage_api is not None:
        _patch_workspace_storage(storage_api, storage_obj, workspace_name, update)

    return {"name": workspace_name}


@app.delete(
    "/workspaces/{workspace_name}",
    status_code=HTTPStatus.NO_CONTENT,
    tags=["Workspaces"],
    summary="Delete a workspace",
    description="Deletes the workspace Storage and Datalab resources that exist.",
    responses={
        204: {"description": "Workspace deleted."},
        404: {"description": "Workspace not found."},
    },
)
async def delete_workspace(workspace_name: str = workspace_path_type) -> Response:
    found = False
    for api_version, kind in ((API_STORAGE, KIND_STORAGE), (API_DATALAB, KIND_DATALAB)):
        api = _res_optional(api_version, kind)
        if api is None:
            continue
        try:
            api.delete(name=workspace_name, namespace=current_namespace())
            found = True
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise
    if not found:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Workspace not found")

    return Response(status_code=HTTPStatus.NO_CONTENT)


def _resource_ready(resource: Any) -> bool:
    conditions = _datalab_status(resource).get("conditions") or []
    return any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions) and not any(
        item.get("type") == "Synced" and item.get("status") == "False" for item in conditions
    )


def _published_stores(connections: Sequence[Connection]) -> list[Store]:
    types = {"postgres": StoreType.DATABASE, "mongo": StoreType.DOCUMENT, "redis": StoreType.CACHE}
    return [
        Store(
            name=connection.name,
            instance=connection.name,
            type=types[connection.type],
            storage=None,
            backup_storage=None,
            creation_timestamp=None,
        )
        for connection in connections
        if connection.type in types
    ]


def _vclusters_from_datalab(datalab: Any, *, management: bool = False) -> list[VCluster]:
    if not management:
        published_clusters: dict[str, VCluster] = {}
        for entry in _datalab_status(datalab).get("connections") or []:
            if not isinstance(entry, dict) or entry.get("type") != "vcluster" or not entry.get("instance"):
                continue
            try:
                group = VClusterGroup.model_validate(
                    {
                        "name": entry.get("group"),
                        "namespace": entry.get("targetNamespace"),
                        "role": entry.get("role"),
                        "ready": entry.get("ready", False),
                    }
                )
            except ValidationError:
                continue
            cluster = published_clusters.setdefault(entry["instance"], VCluster(name=entry["instance"]))
            if group.name != "cluster-admin":
                cluster.groups.append(group)
        return [published_clusters[name] for name in sorted(published_clusters)]
    instances = (_to_spec_dict(datalab) or {}).get("vclusters") or {}
    return [
        VCluster(
            name=name,
            groups=[VClusterGroup.model_validate(group) for group in settings.get("groups") or [] if group.get("name") != "cluster-admin"],
        )
        for name, settings in sorted(instances.items())
    ]


def _get_datalab_vclusters(workspace_name: str) -> tuple[Any, dict[str, Any]]:
    api = _res_optional(API_DATALAB, KIND_DATALAB)
    if api is None:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail={"error": "provider_datalab_not_installed"})
    try:
        datalab = api.get(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Workspace not found") from e
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail="Could not read virtual clusters") from e
    return api, _to_spec_dict(datalab) or {}


@app.post(
    "/workspaces/{workspace_name}/vclusters/{instance}/groups",
    status_code=HTTPStatus.CREATED,
    response_model=VClusterGroup,
    response_model_exclude_none=True,
    tags=["Virtual clusters"],
    summary="Add a namespace access group to a virtual cluster",
)
async def create_vcluster_group(
    request: Request,
    data: VClusterGroupCreate,
    workspace_name: str = workspace_path_type,
    instance: str = Path(pattern=RESOURCE_NAME_PATTERN, max_length=30),
) -> VClusterGroup:
    _require_workspace_permission(request, workspace_name, UserPermission.MANAGE_VCLUSTERS)
    api, spec = _get_datalab_vclusters(workspace_name)
    settings = (spec.get("vclusters") or {}).get(instance)
    if settings is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Virtual cluster not found")
    groups = settings.get("groups") or []
    name = data.name or f"{data.namespace}-{data.role}"
    if len(name) > 30:
        name = f"{name[:21].rstrip('-')}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
    if name == "cluster-admin" or any(group.get("name") == name for group in groups):
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail="Group name already exists or is reserved")
    if len(groups) >= 20:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail="A virtual cluster permits at most 20 declared groups")
    group = VClusterGroup(name=name, namespace=data.namespace, role=data.role)
    path = f"/spec/vclusters/{instance}"
    try:
        api.patch(
            name=workspace_name,
            namespace=current_namespace(),
            body=[
                {"op": "test", "path": path, "value": settings},
                {"op": "add", "path": f"{path}/groups", "value": [*groups, group.model_dump(exclude_none=True)]},
            ],
            content_type="application/json-patch+json",
        )
    except ApiException as e:
        if e.status in (HTTPStatus.CONFLICT, HTTPStatus.UNPROCESSABLE_ENTITY):
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Virtual cluster configuration changed; reload and try again"
            ) from e
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail="Could not add virtual cluster group") from e
    return group


POLL_INTERVAL_SECONDS = 10


def _get_datalab_for_sessions(workspace_name: str) -> tuple[Any, Any, dict[str, Any], list[Any]]:
    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    if datalab_api is None:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={
                "error": "provider_datalab_not_installed",
                "message": "Datalab CRD not present; cannot manage sessions.",
            },
        )

    try:
        datalab = datalab_api.get(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise

    spec = _to_spec_dict(datalab) or {}
    return datalab_api, datalab, spec, _session_declarations(spec)


def _session_create_patch(spec: dict[str, Any], session: SessionCreate) -> list[dict[str, Any]]:
    item = _session_item(session.name, session.state)
    if isinstance(spec.get("sessions"), list):
        return [{"op": "add", "path": "/spec/sessions/-", "value": item}]

    return [
        {
            "op": "replace" if "sessions" in spec else "add",
            "path": "/spec/sessions",
            "value": [item],
        }
    ]


def _patch_datalab_sessions(datalab_api: Any, workspace_name: str, patch_body: list[dict[str, Any]]) -> None:
    try:
        datalab_api.patch(
            name=workspace_name,
            namespace=current_namespace(),
            body=patch_body,
            content_type="application/json-patch+json",
        )
    except ApiException as e:
        msg = f"Patching sessions for workspace '{workspace_name}' failed"
        logger.warning("%s: %s", msg, e)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail={"error": msg, "exception": str(e)},
        ) from e


@app.get(
    "/workspaces/{workspace_name}/sessions",
    status_code=HTTPStatus.OK,
    response_model=list[Session],
    response_model_exclude_none=True,
    tags=["Sessions"],
    summary="List sessions for a workspace",
    responses={
        200: {"description": "Workspace sessions returned."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace not found."},
        503: {"description": "Datalab CRD unavailable."},
    },
)
async def list_workspace_sessions(request: Request, workspace_name: str = workspace_path_type) -> list[Session]:
    _require_workspace_permission(request, workspace_name, UserPermission.VIEW_SESSIONS)
    _, datalab, _, _ = _get_datalab_for_sessions(workspace_name)
    return _sessions_from_datalab(datalab)


@app.post(
    "/workspaces/{workspace_name}/sessions",
    status_code=HTTPStatus.CREATED,
    response_model=Session,
    response_model_exclude_none=True,
    tags=["Sessions"],
    summary="Add a session to a workspace",
    responses={
        201: {"description": "Session declared."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace not found."},
        409: {"description": "Session already exists."},
        503: {"description": "Datalab CRD unavailable."},
    },
)
async def create_workspace_session(
    request: Request,
    data: SessionCreate,
    workspace_name: str = workspace_path_type,
) -> Session:
    _require_workspace_permission(request, workspace_name, UserPermission.MANAGE_SESSIONS)
    datalab_api, _, spec, spec_sessions = _get_datalab_for_sessions(workspace_name)

    if _find_session(spec_sessions, data.name) is not None:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail={"error": "session_exists", "session": data.name},
        )

    max_sessions = _max_sessions()
    if len(spec_sessions) >= max_sessions:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "error": "session_limit_exceeded",
                "max_sessions": max_sessions,
            },
        )

    _patch_datalab_sessions(datalab_api, workspace_name, _session_create_patch(spec, data))
    return Session(name=data.name, state=data.state, url=None, ready=False)


@app.patch(
    "/workspaces/{workspace_name}/sessions/{session_id}",
    status_code=HTTPStatus.ACCEPTED,
    response_model=Session,
    response_model_exclude_none=True,
    tags=["Sessions"],
    summary="Change a session state",
    responses={
        202: {"description": "Session state update accepted."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace/session not found."},
        503: {"description": "Datalab CRD unavailable."},
    },
)
async def update_workspace_session_state(
    request: Request,
    data: SessionStateUpdate,
    workspace_name: str = workspace_path_type,
    session_id: str = Path(..., pattern=SESSION_NAME_PATTERN, description="Session identifier"),
) -> Session:
    _require_workspace_permission(request, workspace_name, UserPermission.MANAGE_SESSIONS)
    datalab_api, datalab, _, spec_sessions = _get_datalab_for_sessions(workspace_name)
    patch_body = _session_state_patch(spec_sessions, session_id, data.state)
    if not patch_body:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={"error": "session_not_found", "session": session_id},
        )

    _patch_datalab_sessions(datalab_api, workspace_name, patch_body)
    payload = _session_status_payload(datalab, session_id)
    url = _http_url(payload.get("url")) if data.state == SessionState.STARTED else None
    return Session(
        name=session_id,
        state=data.state,
        url=url,
        ready=bool(url and _session_runtime_ready(payload)),
    )


@app.delete(
    "/workspaces/{workspace_name}/sessions/{session_id}",
    status_code=HTTPStatus.NO_CONTENT,
    tags=["Sessions"],
    summary="Remove a session from a workspace",
    responses={
        204: {"description": "Session removed."},
        403: {"description": "Forbidden."},
        404: {"description": "Workspace/session not found."},
        503: {"description": "Datalab CRD unavailable."},
    },
)
async def delete_workspace_session(
    request: Request,
    workspace_name: str = workspace_path_type,
    session_id: str = Path(..., pattern=SESSION_NAME_PATTERN, description="Session identifier"),
) -> Response:
    _require_workspace_permission(request, workspace_name, UserPermission.MANAGE_SESSIONS)
    datalab_api, _, _, spec_sessions = _get_datalab_for_sessions(workspace_name)
    index = _session_index(spec_sessions, session_id)
    if index is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={"error": "session_not_found", "session": session_id},
        )

    _patch_datalab_sessions(datalab_api, workspace_name, [{"op": "remove", "path": f"/spec/sessions/{index}"}])
    return Response(status_code=HTTPStatus.NO_CONTENT)


@app.get(
    "/workspaces/{workspace_name}/sessions/{session_id}",
    status_code=HTTPStatus.OK,
    tags=["Sessions"],
    summary="Enable a session and read its published URL",
    description="On-demand session enablement. Readiness and destination come from Datalab status. Pending sessions return 202.",
    responses={
        200: {"description": "Ready: JSON with the published URL."},
        307: {"description": "Browser redirect to the published URL."},
        202: {"description": 'Starting: JSON {"status":"starting"} with Retry-After: 10.'},
        404: {"description": "Workspace/session not found or enabling unavailable."},
        502: {"description": "Backend failure while enabling session."},
    },
)
async def get_workspace_session(
    request: Request,
    workspace_name: str = workspace_path_type,
    session_id: str = Path(..., pattern=SESSION_NAME_PATTERN, description="Session identifier"),
) -> Response:
    _require_workspace_permission(request, workspace_name, UserPermission.VIEW_SESSIONS)

    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    if datalab_api is None:
        msg = f"Session enabling unavailable: CRD {CRD_DATALAB} not found"
        logger.warning(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

    dl = _get_cr(API_DATALAB, KIND_DATALAB, workspace_name, required=False)
    if dl is None:
        msg = f"Session enabling failed: workspace '{workspace_name}' not found"
        logger.warning(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

    spec = _to_spec_dict(dl) or {}
    spec_sessions = _session_declarations(spec)
    spec_session = _find_session(spec_sessions, str(session_id))
    session = next((session for session in _sessions_from_datalab(dl) if session.name == session_id), None)

    if session is None and (spec_session is None or _session_state(spec_session) is None):
        msg = f"Session enabling unavailable: session '{session_id}' is not declared or published"
        logger.info(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})
    if spec_session is not None and _session_state(spec_session) != SESSION_STATE_STARTED:
        patch_body = _session_state_patch(spec_sessions, str(session_id), SessionState.STARTED)
        logger.info(
            "Starting stopped session '%s' for workspace '%s'.",
            session_id,
            workspace_name,
        )
        try:
            datalab_api.patch(
                name=workspace_name,
                namespace=current_namespace(),
                body=patch_body,
                content_type="application/json-patch+json",
            )
        except ApiException as e:
            msg = f"Starting session '{session_id}' for workspace '{workspace_name}' failed"
            logger.warning("%s: %s", msg, e)
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail={"error": msg, "exception": str(e)},
            ) from e

    url = session.url if session is not None else None
    ready = session is not None and session.ready and (spec_session is None or _session_state(spec_session) == SESSION_STATE_STARTED)

    accept_header = request.headers.get("accept", "").lower()
    if "text/html" in accept_header:
        if ready and url:
            return RedirectResponse(url, headers={"Cache-Control": "no-store"})
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>Session unavailable</title>"
            "<p>The session is not ready. Return to Sessions and refresh to check its published URL.</p>",
            status_code=HTTPStatus.ACCEPTED,
            headers={"Cache-Control": "no-store", "Retry-After": str(POLL_INTERVAL_SECONDS)},
        )

    if ready:
        return JSONResponse(
            {"url": url},
            status_code=HTTPStatus.OK,
            headers={"Cache-Control": "no-store"},
        )
    payload = {"status": "starting"}
    if url:
        payload["url"] = str(url)
    return JSONResponse(
        payload,
        status_code=HTTPStatus.ACCEPTED,
        headers={
            "Retry-After": str(POLL_INTERVAL_SECONDS),
            "Cache-Control": "no-store",
        },
    )
