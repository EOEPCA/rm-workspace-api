# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
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
