# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest import mock

import pytest

from workspace_api import config, views
from workspace_api.models import Store, StoreType, WorkspaceEdit
from workspace_api.views import (
    _available_store_types,
)


def test_available_store_types_exclude_configured_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISABLE_STORES", "false")
    monkeypatch.setattr(config, "DISABLED_STORE_TYPES", "database,cache")
    monkeypatch.setattr(
        "workspace_api.views._datalab_crd_store_fields",
        lambda: {"databases", "documentStores", "cacheStores"},
    )
    monkeypatch.setattr("workspace_api.views._store_type_crd_present", lambda _store_type: True)

    assert _available_store_types(datalab_installed=True) == [StoreType.DOCUMENT]


def test_available_store_types_require_backing_crds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISABLE_STORES", "false")
    monkeypatch.setattr(config, "DISABLED_STORE_TYPES", "")
    monkeypatch.setattr(
        "workspace_api.views._datalab_crd_store_fields",
        lambda: {"databases", "vectorStores", "cacheStores", "documentStores"},
    )
    monkeypatch.setattr("workspace_api.views._store_type_crd_present", lambda store_type: store_type is StoreType.DATABASE)

    assert _available_store_types(datalab_installed=True) == [StoreType.DATABASE]


def test_available_store_types_can_disable_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISABLE_STORES", "true")
    monkeypatch.setattr(config, "DISABLED_STORE_TYPES", "")
    monkeypatch.setattr(
        "workspace_api.views._datalab_crd_store_fields",
        lambda: {"databases", "vectorStores", "cacheStores", "documentStores"},
    )
    monkeypatch.setattr("workspace_api.views._store_type_crd_present", lambda _store_type: True)

    assert _available_store_types(datalab_installed=True) == []


def test_workspace_edit_deduplicates_stores_by_type_and_name() -> None:
    edit = WorkspaceEdit(
        add_stores=[
            Store(name="analytics", type=StoreType.DATABASE, storage=None, backup_storage=None, creation_timestamp=None),
            Store(name="analytics", type=StoreType.DATABASE, storage=None, backup_storage=None, creation_timestamp=None),
            Store(name="analytics", type=StoreType.DOCUMENT, storage=None, backup_storage=None, creation_timestamp=None),
        ]
    )

    assert [(store.type, store.name) for store in edit.add_stores] == [
        (StoreType.DATABASE, "analytics"),
        (StoreType.DOCUMENT, "analytics"),
    ]


def test_store_types_do_not_use_another_crd_version(monkeypatch: pytest.MonkeyPatch) -> None:
    crd = {
        "spec": {
            "versions": [
                {
                    "name": "v1beta1",
                    "served": True,
                    "schema": {"openAPIV3Schema": {"properties": {"spec": {"properties": {"databases": {}}}}}},
                }
            ]
        }
    }
    monkeypatch.setattr(views.k8s_client, "ApiextensionsV1Api", lambda: SimpleNamespace(read_custom_resource_definition=lambda _name: crd))
    backing = mock.Mock(return_value=True)
    monkeypatch.setattr(views, "_store_type_crd_present", backing)

    assert _available_store_types(datalab_installed=True) == []
    backing.assert_not_called()
