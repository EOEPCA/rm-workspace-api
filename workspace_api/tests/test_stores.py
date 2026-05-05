# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime

import pytest

from workspace_api import config
from workspace_api.models import ROLE_TO_PERMISSIONS, Store, StoreType, UserPermission, WorkspaceEdit
from workspace_api.views import (
    _available_store_types,
    _default_storage_for_type,
    _put_store_credentials,
    _store_credentials_from_envs,
    _store_field_for_type,
    _stores_from_map,
)


def test_store_permissions_are_role_defaults() -> None:
    assert UserPermission.VIEW_STORES in ROLE_TO_PERMISSIONS["ws_access"]
    assert UserPermission.VIEW_STORES in ROLE_TO_PERMISSIONS["ws_admin"]
    assert UserPermission.MANAGE_STORES in ROLE_TO_PERMISSIONS["ws_admin"]

    permission_values = {permission.value for permission in UserPermission}
    assert "VIEW_DATABASES" not in permission_values
    assert "MANAGE_DATABASES" not in permission_values


def test_store_types_map_to_provider_datalab_fields() -> None:
    assert _store_field_for_type(StoreType.DATABASE) == "databases"
    assert _store_field_for_type(StoreType.VECTOR) == "vectorStores"
    assert _store_field_for_type(StoreType.CACHE) == "cacheStores"
    assert _store_field_for_type(StoreType.DOCUMENT) == "documentStores"


def test_available_store_types_merge_crd_fields_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISABLE_STORES", "false")
    monkeypatch.setattr(config, "DISABLED_STORE_TYPES", "postgres,redis")
    monkeypatch.setattr(
        "workspace_api.views._datalab_crd_store_fields",
        lambda: {"databases", "vectorStores", "cacheStores"},
    )

    assert _available_store_types(datalab_installed=True) == [StoreType.VECTOR]


def test_available_store_types_can_disable_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISABLE_STORES", "true")
    monkeypatch.setattr(config, "DISABLED_STORE_TYPES", "")
    monkeypatch.setattr(
        "workspace_api.views._datalab_crd_store_fields",
        lambda: {"databases", "vectorStores", "cacheStores", "documentStores"},
    )

    assert _available_store_types(datalab_installed=True) == []


def test_store_types_have_provider_defaults() -> None:
    assert _default_storage_for_type(StoreType.DATABASE) == "1Gi"
    assert _default_storage_for_type(StoreType.VECTOR) == "1Gi"
    assert _default_storage_for_type(StoreType.CACHE) == "1Gi"
    assert _default_storage_for_type(StoreType.DOCUMENT) == "10Gi"


def test_stores_from_provider_datalab_map() -> None:
    created = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    stores = _stores_from_map(
        {
            "documentStores": {
                "documents": {"storage": " 10Gi "},
            }
        },
        "documentStores",
        StoreType.DOCUMENT,
        created,
    )

    assert stores == [
        Store(
            name="documents",
            type=StoreType.DOCUMENT,
            storage="10Gi",
            backup_storage=None,
            creation_timestamp=created,
        )
    ]


def test_store_credentials_are_grouped_by_type_and_name() -> None:
    store_credentials: dict[StoreType, dict[str, dict[str, str]]] = {}

    _put_store_credentials(
        store_credentials,
        StoreType.DATABASE,
        "analytics",
        {
            "url": "postgresql://postgres@example",
            "username": None,
            "password": "secret",
        },
    )

    assert store_credentials == {
        StoreType.DATABASE: {
            "analytics": {
                "url": "postgresql://postgres@example",
                "password": "secret",
            }
        }
    }


def test_store_credentials_from_provider_datalab_secret_keys() -> None:
    credentials = _store_credentials_from_envs(
        {
            "DATABASE_URL": "postgresql://postgres@example/dev",
            "DATABASE_URL_EXTERNAL": "postgresql://postgres@external.example/dev",
            "DATABASE_NAME": "dev",
            "DATABASE_HOST": "pg0-primary.s-jeff.svc",
            "DATABASE_PORT": "5432",
            "DATABASE_USER": "postgres",
            "DATABASE_PASSWORD": "db-secret",
            "QDRANT_PROD_API_KEY": "qdrant-write",
            "QDRANT_PROD_READ_API_KEY": "qdrant-read",
            "REDIS_PROD_PASSWORD": "redis-secret",
            "MONGO_PROD_PASSWORD": "mongo-secret",
        },
        ["dev", "prod"],
    )

    assert credentials == {
        StoreType.DATABASE: {
            "pg0": {
                "host": "pg0-primary.s-jeff.svc",
                "port": "5432",
                "username": "postgres",
                "password": "db-secret",
                "urls": {
                    "dev": "postgresql://postgres@example/dev",
                    "prod": "postgresql://postgres@example/prod",
                },
                "external_urls": {
                    "dev": "postgresql://postgres@external.example/dev",
                    "prod": "postgresql://postgres@external.example/prod",
                },
            }
        },
        StoreType.VECTOR: {
            "prod": {
                "api_key": "qdrant-write",
                "read_api_key": "qdrant-read",
            }
        },
        StoreType.CACHE: {
            "prod": {
                "password": "redis-secret",
            }
        },
        StoreType.DOCUMENT: {
            "prod": {
                "password": "mongo-secret",
            }
        },
    }


def test_store_credentials_from_expanded_provider_datalab_secret_keys() -> None:
    credentials = _store_credentials_from_envs(
        {
            "PG_ANALYTICS_HOST": "analytics-primary.s-jeff.svc",
            "PG_ANALYTICS_PORT": "5432",
            "PG_ANALYTICS_USER": "postgres",
            "PG_ANALYTICS_PASSWORD": "db-secret",
            "PG_ANALYTICS_DATABASES": "prod,dev",
            "PG_ANALYTICS_PROD_URL": "postgresql://postgres@analytics/prod",
            "PG_ANALYTICS_DEV_URL_EXTERNAL": "postgresql://postgres@external/dev",
            "MONGO_DOCS_HOST": "mongodb-docs-svc.s-jeff.svc",
            "MONGO_DOCS_PORT": "27017",
            "MONGO_DOCS_DATABASE": "docs",
            "MONGO_DOCS_AUTH_SOURCE": "admin",
            "MONGO_DOCS_USER": "docs-app",
            "MONGO_DOCS_PASSWORD": "mongo-secret",
            "MONGO_DOCS_URI": "mongodb://docs-app:mongo-secret@mongodb-docs-svc.s-jeff.svc:27017/docs?authSource=admin",
            "REDIS_CACHE_HOST": "cache.s-jeff.svc",
            "REDIS_CACHE_PORT": "6379",
            "REDIS_CACHE_USER": "default",
            "REDIS_CACHE_DATABASE": "0",
            "REDIS_CACHE_PASSWORD": "redis-secret",
            "REDIS_CACHE_URL": "redis://default:redis-secret@cache.s-jeff.svc:6379/0",
            "QDRANT_EMBEDDINGS_HOST": "qdrant-embeddings.s-jeff.svc",
            "QDRANT_EMBEDDINGS_PORT": "6333",
            "QDRANT_EMBEDDINGS_GRPC_PORT": "6334",
            "QDRANT_EMBEDDINGS_URL": "http://qdrant-embeddings.s-jeff.svc:6333",
            "QDRANT_EMBEDDINGS_API_KEY": "qdrant-write",
            "QDRANT_EMBEDDINGS_READ_API_KEY": "qdrant-read",
        },
        database_hosts={"analytics": ["prod", "dev"]},
    )

    assert credentials[StoreType.DATABASE]["analytics"]["host"] == "analytics-primary.s-jeff.svc"
    assert credentials[StoreType.DATABASE]["analytics"]["urls"] == {"prod": "postgresql://postgres@analytics/prod"}
    assert credentials[StoreType.DATABASE]["analytics"]["external_urls"] == {"dev": "postgresql://postgres@external/dev"}
    assert credentials[StoreType.DOCUMENT]["docs"]["uri"].startswith("mongodb://docs-app:")
    assert credentials[StoreType.CACHE]["cache"]["url"] == "redis://default:redis-secret@cache.s-jeff.svc:6379/0"
    assert credentials[StoreType.VECTOR]["embeddings"] == {
        "host": "qdrant-embeddings.s-jeff.svc",
        "port": "6333",
        "grpc_port": "6334",
        "url": "http://qdrant-embeddings.s-jeff.svc:6333",
        "api_key": "qdrant-write",
        "read_api_key": "qdrant-read",
    }


def test_workspace_edit_deduplicates_stores_by_type_and_name() -> None:
    edit = WorkspaceEdit(
        add_stores=[
            Store(name="analytics", type=StoreType.DATABASE, storage=None, backup_storage=None, creation_timestamp=None),
            Store(name="analytics", type=StoreType.DATABASE, storage=None, backup_storage=None, creation_timestamp=None),
            Store(name="analytics", type=StoreType.VECTOR, storage=None, backup_storage=None, creation_timestamp=None),
        ]
    )

    assert [(store.type, store.name) for store in edit.add_stores] == [
        (StoreType.DATABASE, "analytics"),
        (StoreType.VECTOR, "analytics"),
    ]
