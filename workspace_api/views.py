# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from http import HTTPStatus
from typing import Any

import kubernetes.client
import kubernetes.client.rest
import requests
from fastapi import HTTPException, Path, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from pydantic import SecretStr
from slugify import slugify

from workspace_api import app, config, templates

from .models import (
    Bucket,
    BucketAccessRequest,
    BucketLifecycleRule,
    BucketLifecycleRuleMode,
    BucketPermission,
    ContainerRegistryCredentials,
    Credentials,
    Datalab,
    Membership,
    MembershipRole,
    Storage,
    Store,
    StoreType,
    UserContext,
    UserPermission,
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


def _provider_environment() -> str:
    return str(getattr(config, "PROVIDER_ENVIRONMENT", "datalab") or "datalab").strip() or "datalab"


def _provider_environment_annotations(annotation_key: str) -> dict[str, str]:
    return {annotation_key: _provider_environment()}


def _workspace_name_pattern() -> str:
    p = (getattr(config, "PREFIX_FOR_NAME", "") or "").strip().rstrip("-")
    if p:
        return rf"^{re.escape(p)}-"
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
SESSION_STATE_STARTED = "started"
SESSION_STATE_STOPPED = "stopped"
STORAGE_ENVIRONMENT_ANNOTATION = "storages.pkg.internal/environment"
DATALAB_ENVIRONMENT_ANNOTATION = "datalabs.pkg.internal/environment"
STORE_TYPE_CRDS = {
    StoreType.DATABASE: "postgresclusters.postgres-operator.crunchydata.com",
    StoreType.VECTOR: "qdrantclusters.qdrant.io",
    StoreType.CACHE: "redis.redis.redis.opstreelabs.in",
    StoreType.DOCUMENT: "mongodbcommunity.mongodbcommunity.mongodb.com",
}


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


def _session_name(item: Any) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        return _clean_str(item.get("name"))
    return None


def _session_state(item: Any) -> str:
    if isinstance(item, dict):
        return (_clean_str(item.get("state")) or SESSION_STATE_STARTED).lower()
    return SESSION_STATE_STARTED


def _session_item(name: str, state: str) -> dict[str, str]:
    return {"name": name, "state": state}


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


def _datalab_declares_session(workspace_name: str, session_id: str) -> bool:
    if session_id != DEFAULT_SESSION_NAME:
        return False

    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    if datalab_api is None:
        return False

    try:
        datalab = datalab_api.get(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return False
        raise

    spec = _to_spec_dict(datalab) or {}
    return _find_session(_session_declarations(spec), session_id) is not None


def _session_start_patch(sessions: Sequence[Any], session_id: str) -> list[dict[str, Any]]:
    index = _session_index(sessions, session_id)
    if index is None:
        return []

    session = sessions[index]
    path = f"/spec/sessions/{index}"
    if isinstance(session, dict):
        return [
            {
                "op": "replace" if "state" in session else "add",
                "path": f"{path}/state",
                "value": SESSION_STATE_STARTED,
            }
        ]

    return [{"op": "replace", "path": path, "value": _session_item(session_id, SESSION_STATE_STARTED)}]


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
                    min_age=raw_rule.get("minAge") or raw_rule.get("min_age"),
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
        StoreType.VECTOR: "vectorStores",
        StoreType.CACHE: "cacheStores",
        StoreType.DOCUMENT: "documentStores",
    }[store_type]


def _default_storage_for_type(store_type: StoreType) -> str:
    return {
        StoreType.DATABASE: "1Gi",
        StoreType.VECTOR: "1Gi",
        StoreType.CACHE: "1Gi",
        StoreType.DOCUMENT: "10Gi",
    }[store_type]


def _store_type_from_config(raw: str) -> StoreType | None:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "database": StoreType.DATABASE,
        "databases": StoreType.DATABASE,
        "postgres": StoreType.DATABASE,
        "postgresql": StoreType.DATABASE,
        "vector": StoreType.VECTOR,
        "vector_store": StoreType.VECTOR,
        "vectorstores": StoreType.VECTOR,
        "qdrant": StoreType.VECTOR,
        "cache": StoreType.CACHE,
        "caches": StoreType.CACHE,
        "cache_store": StoreType.CACHE,
        "cachestores": StoreType.CACHE,
        "redis": StoreType.CACHE,
        "document": StoreType.DOCUMENT,
        "documents": StoreType.DOCUMENT,
        "document_store": StoreType.DOCUMENT,
        "documentstores": StoreType.DOCUMENT,
        "mongodb": StoreType.DOCUMENT,
        "mongo": StoreType.DOCUMENT,
    }
    return aliases.get(normalized)


def _disabled_store_types() -> set[StoreType]:
    if _as_bool(getattr(config, "DISABLE_STORES", "false")):
        return set(StoreType)

    raw = str(getattr(config, "DISABLED_STORE_TYPES", "") or "")
    parts = [part.strip() for part in raw.replace(";", ",").split(",")]
    if any(part.lower() in {"*", "all", "true", "yes", "1"} for part in parts):
        return set(StoreType)

    return {store_type for part in parts if (store_type := _store_type_from_config(part)) is not None}


def _get_nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _schema_value(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _datalab_crd_store_fields() -> set[str]:
    try:
        crd = k8s_client.ApiextensionsV1Api().read_custom_resource_definition(CRD_DATALAB)
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return set()
        raise

    crd_dict = crd.to_dict() if hasattr(crd, "to_dict") else crd
    versions = _get_nested(crd_dict, "spec", "versions") or []
    if not isinstance(versions, list):
        return set()

    api_version = API_DATALAB.rsplit("/", 1)[-1]
    selected = next((v for v in versions if isinstance(v, dict) and v.get("name") == api_version), None)
    if selected is None:
        selected = next((v for v in versions if isinstance(v, dict) and v.get("served")), None)
    if selected is None:
        return set()

    schema = _schema_value(selected.get("schema") or {}, "openAPIV3Schema", "open_apiv3_schema") or {}
    spec_properties = _get_nested(schema, "properties", "spec", "properties") or {}
    if not isinstance(spec_properties, dict):
        return set()

    return {field for field in (_store_field_for_type(store_type) for store_type in StoreType) if field in spec_properties}


def _store_type_crd_present(store_type: StoreType) -> bool:
    crd_name = STORE_TYPE_CRDS.get(store_type)
    return bool(crd_name and _crd_exists(crd_name))


def _available_store_types(datalab_installed: bool) -> list[StoreType]:
    if not datalab_installed:
        return []

    supported_fields = _datalab_crd_store_fields()
    disabled = _disabled_store_types()
    return [
        store_type
        for store_type in StoreType
        if store_type not in disabled and _store_field_for_type(store_type) in supported_fields and _store_type_crd_present(store_type)
    ]


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
    try:
        storage_api = _res_required(API_STORAGE, KIND_STORAGE)
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


def _b64decode_secret_data(data: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (data or {}).items():
        if v is None:
            continue
        out[k] = base64.b64decode(v).decode("utf-8")
    return out


def _clean_str(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return None


def _compact_credentials(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


def _put_store_credentials(
    store_credentials: dict[StoreType, dict[str, dict[str, Any]]],
    store_type: StoreType,
    store_name: str | None,
    values: dict[str, Any],
) -> None:
    name = (store_name or "default").strip() or "default"
    credentials = {key: value for key, value in values.items() if value}
    if not credentials:
        return

    store_credentials.setdefault(store_type, {}).setdefault(name, {}).update(credentials)


def _store_name_from_secret_part(raw: str) -> str:
    return raw.strip().lower().replace("_", "-")


def _secret_store_key(prefix: str, store_name: str, suffix: str) -> str:
    normalized_store = re.sub(r"[^A-Za-z0-9]+", "_", store_name).strip("_").upper()
    return f"{prefix}_{normalized_store}_{suffix}"


def _pg_secret_key(cluster_name: str, suffix: str) -> str:
    return _secret_store_key("POSTGRES", cluster_name, suffix)


def _pg_db_secret_key(cluster_name: str, database_name: str, suffix: str) -> str:
    normalized_cluster = re.sub(r"[^A-Za-z0-9]+", "_", cluster_name).strip("_").upper()
    normalized_database = re.sub(r"[^A-Za-z0-9]+", "_", database_name).strip("_").upper()
    return f"POSTGRES_{normalized_cluster}_{normalized_database}_{suffix}"


def _pg_secret_value(envs: Mapping[str, str], cluster_name: str, suffix: str) -> str | None:
    return _clean_str(envs.get(_pg_secret_key(cluster_name, suffix)))


def _pg_db_secret_value(envs: Mapping[str, str], cluster_name: str, database_name: str, suffix: str) -> str | None:
    return _clean_str(envs.get(_pg_db_secret_key(cluster_name, database_name, suffix)))


def _store_credentials_from_envs(
    envs: dict[str, str],
    database_hosts: Mapping[str, Sequence[str]] | None = None,
) -> dict[StoreType, dict[str, dict[str, Any]]]:
    store_credentials: dict[StoreType, dict[str, dict[str, Any]]] = {}

    for cluster_name, host_database_names_raw in (database_hosts or {}).items():
        host_database_names = [name for name in host_database_names_raw if name]
        if not host_database_names:
            continue

        host = _pg_secret_value(envs, cluster_name, "HOST")
        port = _pg_secret_value(envs, cluster_name, "PORT")
        username = _pg_secret_value(envs, cluster_name, "USER")
        password = _pg_secret_value(envs, cluster_name, "PASSWORD")
        host_external = _pg_secret_value(envs, cluster_name, "HOST_EXTERNAL")
        urls = {name: url for name in host_database_names if (url := _pg_db_secret_value(envs, cluster_name, name, "URL"))}
        external_urls = {
            name: url for name in host_database_names if (url := _pg_db_secret_value(envs, cluster_name, name, "URL_EXTERNAL"))
        }

        if host or username or password or urls or external_urls:
            _put_store_credentials(
                store_credentials,
                StoreType.DATABASE,
                cluster_name,
                {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "host_external": host_external,
                    "databases": ",".join(host_database_names),
                    "urls": urls,
                    "external_urls": external_urls,
                },
            )

    for key, value in envs.items():
        cleaned_value = _clean_str(value)
        if not cleaned_value:
            continue

        if match := re.fullmatch(r"MONGO_(.+?)_(AUTH_SOURCE|HOST|PORT|DATABASE|USER|PASSWORD|URI)", key):
            fields = {
                "HOST": "host",
                "PORT": "port",
                "DATABASE": "database",
                "AUTH_SOURCE": "auth_source",
                "USER": "username",
                "PASSWORD": "password",
                "URI": "uri",
            }
            _put_store_credentials(
                store_credentials,
                StoreType.DOCUMENT,
                _store_name_from_secret_part(match.group(1)),
                {fields[match.group(2)]: cleaned_value},
            )
            continue

        if match := re.fullmatch(r"REDIS_(.+?)_(HOST|PORT|USER|DATABASE|PASSWORD|URL)", key):
            fields = {
                "HOST": "host",
                "PORT": "port",
                "USER": "username",
                "DATABASE": "database",
                "PASSWORD": "password",
                "URL": "url",
            }
            _put_store_credentials(
                store_credentials,
                StoreType.CACHE,
                _store_name_from_secret_part(match.group(1)),
                {fields[match.group(2)]: cleaned_value},
            )
            continue

        if match := re.fullmatch(r"QDRANT_(.+?)_(READ_API_KEY|GRPC_PORT|API_KEY|HOST|PORT|URL)", key):
            fields = {
                "HOST": "host",
                "PORT": "port",
                "GRPC_PORT": "grpc_port",
                "URL": "url",
                "READ_API_KEY": "read_api_key",
                "API_KEY": "api_key",
            }
            _put_store_credentials(
                store_credentials,
                StoreType.VECTOR,
                _store_name_from_secret_part(match.group(1)),
                {fields[match.group(2)]: cleaned_value},
            )
            continue

        if match := re.fullmatch(r"QDRANT_(.+)_READ_API_KEY", key):
            _put_store_credentials(
                store_credentials,
                StoreType.VECTOR,
                _store_name_from_secret_part(match.group(1)),
                {"read_api_key": cleaned_value},
            )
            continue

        if match := re.fullmatch(r"QDRANT_(.+)_API_KEY", key):
            _put_store_credentials(
                store_credentials,
                StoreType.VECTOR,
                _store_name_from_secret_part(match.group(1)),
                {"api_key": cleaned_value},
            )
            continue

        if match := re.fullmatch(r"REDIS_(.+)_PASSWORD", key):
            _put_store_credentials(
                store_credentials,
                StoreType.CACHE,
                _store_name_from_secret_part(match.group(1)),
                {"password": cleaned_value},
            )
            continue

        if match := re.fullmatch(r"MONGO_(.+)_PASSWORD", key):
            _put_store_credentials(
                store_credentials,
                StoreType.DOCUMENT,
                _store_name_from_secret_part(match.group(1)),
                {"password": cleaned_value},
            )

    return store_credentials


def _combine_workspace(request: Request, workspace_name: str) -> Workspace:
    storage_cr = _get_cr(API_STORAGE, KIND_STORAGE, workspace_name, required=True)
    if not storage_cr:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "error": f"Storage '{workspace_name}' not found",
                "crd": CRD_STORAGE,
            },
        )

    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    available_store_types = _available_store_types(datalab_api is not None)
    datalab_cr = None
    if datalab_api is not None:
        try:
            datalab_cr = datalab_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise

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
                creation_timestamp=_to_datetime(ts),
            )
        )

    stores: list[Store] = []

    db_hosts = (datalab_spec or {}).get("databases") or {}

    if not isinstance(db_hosts, dict):
        db_hosts = {}

    seen_db: set[str] = set()
    database_hosts: dict[str, list[str]] = {}

    if StoreType.DATABASE in available_store_types:
        for host_name, host_cfg in db_hosts.items():
            if not isinstance(host_cfg, dict):
                continue
            names = host_cfg.get("names") or []
            if not isinstance(names, list):
                continue
            host_key = str(host_name or "").strip() or "pg0"
            database_hosts.setdefault(host_key, [])
            for n in names:
                name = str(n or "").strip()
                if not name or name in seen_db:
                    continue
                seen_db.add(name)
                database_hosts[host_key].append(name)
                stores.append(
                    Store(
                        name=name,
                        type=StoreType.DATABASE,
                        storage=_clean_str(host_cfg.get("storage")),
                        backup_storage=_clean_str(host_cfg.get("backupStorage")),
                        creation_timestamp=dl_created_at,
                    )
                )

    if StoreType.VECTOR in available_store_types:
        stores.extend(_stores_from_map(datalab_spec, "vectorStores", StoreType.VECTOR, dl_created_at))
    if StoreType.CACHE in available_store_types:
        stores.extend(_stores_from_map(datalab_spec, "cacheStores", StoreType.CACHE, dl_created_at))
    if StoreType.DOCUMENT in available_store_types:
        stores.extend(_stores_from_map(datalab_spec, "documentStores", StoreType.DOCUMENT, dl_created_at))

    credentials: Credentials | None = None
    store_credentials: dict[StoreType, dict[str, dict[str, Any]]] = {}
    container_registry_credentials: ContainerRegistryCredentials | None = None

    secret = None
    secret = fetch_secret(f"{workspace_name}-datalab", current_namespace())
    if not secret:
        secret = fetch_secret(f"{workspace_name}", current_namespace())
    if secret and getattr(secret, "data", None):
        try:
            envs = _b64decode_secret_data(secret.data)

            bucketname = _clean_str(envs.get("BUCKET"))
            access = _clean_str(envs.get("AWS_ACCESS_KEY_ID") or envs.get("access") or envs.get("attribute.access"))
            secret_key = _clean_str(envs.get("AWS_SECRET_ACCESS_KEY") or envs.get("secret") or envs.get("attribute.secret"))
            endpoint = _clean_str(
                envs.get("AWS_ENDPOINT_URL") or envs.get("endpoint") or envs.get("attribute.endpoint") or getattr(config, "ENDPOINT", None)
            )
            region = _clean_str(
                envs.get("AWS_REGION") or envs.get("region") or envs.get("attribute.region") or getattr(config, "REGION", None)
            )

            resolved_bucketname = all_buckets[0] if buckets else bucketname

            if resolved_bucketname and access and secret_key and endpoint:
                credentials = Credentials(
                    bucketname=resolved_bucketname,
                    access=access,
                    secret=secret_key,
                    endpoint=endpoint,
                    region=region or "",
                )

            store_credentials = _store_credentials_from_envs(envs, database_hosts)

            reg_user = _clean_str(envs.get("CONTAINER_REGISTRY_USERNAME"))
            reg_pass = _clean_str(envs.get("CONTAINER_REGISTRY_PASSWORD"))
            if reg_user and reg_pass:
                container_registry_credentials = ContainerRegistryCredentials(
                    username=reg_user,
                    password=SecretStr(reg_pass),
                )

        except (KeyError, TypeError, binascii.Error, UnicodeDecodeError) as e:
            logger.warning(
                "Error decoding credentials secret '%s': %s",
                getattr(getattr(secret, "metadata", None), "name", "<unknown>"),
                e,
            )

    creation_timestamp = getattr(storage_cr.metadata, "creationTimestamp", None)
    version = storage_cr.metadata.resourceVersion
    workspace_status = WorkspaceStatus.READY if credentials else WorkspaceStatus.PROVISIONING

    storage = Storage(
        buckets=[
            Bucket(
                name=b,
                discoverable=b in discoverable_buckets,
                lifecycle_rules=bucket_lifecycle_rules.get(b, []),
                creation_timestamp=None,
            )
            for b in all_buckets
        ],
        credentials=credentials,
        bucket_access_requests=relevant_bucket_access_requests,
    )
    datalab = Datalab(
        memberships=memberships,
        available=datalab_api is not None,
        available_store_types=available_store_types,
        stores=stores,
        store_credentials=store_credentials,
        container_registry_credentials=container_registry_credentials,
    )

    user_ctx = request.state.user

    workspace_perms = set()
    if "*" in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"]["*"]
    if workspace_name in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"][workspace_name]

    permission_guards = {
        UserPermission.VIEW_BUCKET_CREDENTIALS: lambda: setattr(storage, "credentials", None),
        UserPermission.VIEW_BUCKETS: lambda: (
            setattr(storage, "buckets", []),  # type: ignore[func-returns-value]
            setattr(storage, "bucket_access_requests", []),  # type: ignore[func-returns-value]
        ),
        UserPermission.VIEW_MEMBERS: lambda: setattr(datalab, "memberships", []),
        UserPermission.VIEW_STORES: lambda: (
            setattr(datalab, "stores", []),  # type: ignore[func-returns-value]
            setattr(datalab, "store_credentials", {}),  # type: ignore[func-returns-value]
            setattr(datalab, "container_registry_credentials", None),  # type: ignore[func-returns-value]
        ),
    }

    for permission, guard in permission_guards.items():
        if permission not in workspace_perms:
            guard()

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
    workspace_name = _with_prefix(slugify(data.preferred_name, max_length=32) or str(uuid.uuid4()))[:63]

    storage_api = _res_required(API_STORAGE, KIND_STORAGE)
    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)

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
        session_mode = str(getattr(config, "SESSION_MODE", "on")).strip().lower()
        use_vcluster = _as_bool(getattr(config, "USE_VCLUSTER", "false"))
        enable_registry = not _as_bool(getattr(config, "DISABLE_DOCKER_REGISTRY", "false"))
        sessions = _initial_sessions_for_mode(session_mode)
        datalab_spec: dict[str, Any] = {
            "users": [slugify(data.default_owner, max_length=32) or str(uuid.uuid4())],
            "secretName": workspace_name,
            "vcluster": use_vcluster,
        }
        if sessions:
            datalab_spec["sessions"] = sessions
        if enable_registry:
            datalab_spec["registry"] = {"enabled": True}

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

        endpoints = []
        if _datalab_declares_session(workspace_name, DEFAULT_SESSION_NAME):
            datalab_path = f"/workspaces/{workspace_name}/sessions/{DEFAULT_SESSION_NAME}"
            datalab_url = make_external_url(request, datalab_path)
            endpoints.append({"id": "Datalab (default)", "url": datalab_url})

        endpoints_data = _to_b64_json(endpoints)

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
        403: {"description": "Forbidden."},
        404: {"description": "Workspace not found."},
        502: {"description": "Backend error while patching cluster resources."},
    },
)
async def update_workspace(request: Request, workspace_name: str, update: WorkspaceEdit) -> dict[str, str]:
    user_ctx = request.state.user

    workspace_perms = set()
    if "*" in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"]["*"]
    if workspace_name in user_ctx["workspaces"]:
        workspace_perms |= user_ctx["workspaces"][workspace_name]

    required_perms: set[UserPermission] = set()

    if update.add_buckets:
        required_perms.add(UserPermission.MANAGE_BUCKETS)

    if update.add_memberships:
        required_perms.add(UserPermission.MANAGE_MEMBERS)

    if update.add_stores:
        required_perms.add(UserPermission.MANAGE_STORES)

    missing = required_perms - workspace_perms
    if missing:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Forbidden")

    storage_api = _res_required(API_STORAGE, KIND_STORAGE)

    try:
        storage_obj = storage_api.get(name=workspace_name, namespace=current_namespace())
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from e
        raise

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

    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)
    available_store_types = _available_store_types(datalab_api is not None)

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

    if add_memberships or add_stores:
        try:
            datalab_obj = datalab_api.get(name=workspace_name, namespace=current_namespace())
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                logger.warning(
                    "Datalab resource '%s' not found; skipping datalab updates.",
                    workspace_name,
                )
            else:
                logger.warning("Reading Datalab '%s' failed: %s", workspace_name, e)
            return {"name": workspace_name}
        except Exception as e:
            logger.warning("Reading Datalab '%s' failed: %s", workspace_name, e)
            return {"name": workspace_name}

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

        for store_type in (StoreType.VECTOR, StoreType.CACHE, StoreType.DOCUMENT):
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
    storage_api = _res_required(API_STORAGE, KIND_STORAGE)
    datalab_api = _res_optional(API_DATALAB, KIND_DATALAB)

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
SESSION_PROBE_TIMEOUT_SECONDS = 5


def _session_probe_url(workspace_name: str, session_id: str) -> str:
    return f"http://{workspace_name}-{session_id}.{workspace_name}.svc.cluster.local/"


def _session_url_ready(url: str) -> bool:
    try:
        response = requests.head(url, allow_redirects=False, timeout=SESSION_PROBE_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        logger.info("Session URL '%s' is not reachable yet: %s", url, e)
        return False

    if 500 <= response.status_code < 600:
        logger.info("Session URL '%s' is not ready yet: status %s", url, response.status_code)
        return False

    return True


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
    if str(session_id) != DEFAULT_SESSION_NAME:
        msg = f"Session enabling unavailable: session '{session_id}' is not managed"
        logger.info(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})

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

    if spec_session is None:
        msg = f"Session enabling unavailable: session '{session_id}' is not declared"
        logger.info(msg)
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail={"error": msg})
    if _session_state(spec_session) != SESSION_STATE_STARTED:
        patch_body = _session_start_patch(spec_sessions, str(session_id))
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
            "p{padding:1em 2em;border-radius:4px;background:#eee;}"
            "small{display:block;margin-top:.75em;color:#555;word-break:break-all;}</style>"
            "<p><span id='msg'>Preparing session, please wait…</span><small id='checked-url'></small></p>"
            "<script>"
            f"const waitBefore={MIN_DISPLAY_SECONDS};"
            "const pollInterval=10000;"
            "function isHttp(u){try{const x=new URL(u);return x.protocol==='http:'||x.protocol==='https:';}catch{return false;}}"
            "function api(){const b=location.href.split('#')[0];const s=b.includes('?')?'&':'?';return b+s+'format=json&ts='+Date.now();}"
            "function showUrl(label,url){"
            "  const el=document.getElementById('checked-url');"
            "  const link=document.createElement('a');"
            "  link.href=url;"
            "  link.textContent=url;"
            "  el.textContent=label+' ';"
            "  el.appendChild(link);"
            "}"
            "function redirect(url) {"
            "  const msg=document.getElementById('msg');"
            "  const link=document.createElement('a');"
            "  link.href=url;"
            "  link.textContent=url;"
            "  showUrl('Session URL:', url);"
            "  msg.textContent='Session ready. Redirecting to ';"
            "  msg.appendChild(link);"
            "  msg.append('...');"
            "  setTimeout(() => location.replace(url), waitBefore * 1000);"
            "}"
            "function check() {"
            "  const apiUrl=api();"
            "  showUrl('Checking:', apiUrl);"
            "  fetch(apiUrl,{headers:{'Accept':'application/json','Cache-Control':'no-store'},cache:'no-store'})"
            "    .then(r => r.json().then(d => ({status:r.status,d})))"
            "    .then(x => {"
            "       const d=x.d;"
            "       if(x.status === 200 && d && d.url && isHttp(d.url)) { redirect(d.url); }"
            "       if(d && d.url && isHttp(d.url)) { showUrl('Session URL:', d.url); }"
            "       throw new Error('status:'+x.status);"
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

    if url and _session_url_ready(_session_probe_url(workspace_name, str(session_id))):
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
