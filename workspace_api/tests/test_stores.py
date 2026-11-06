# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import pytest

from workspace_api import config, views
from workspace_api.models import Store, StoreType, WorkspaceEdit
from workspace_api.views import _available_store_types


@pytest.mark.parametrize(
    "stores, datalab, expected",
    [
        ("mongo", True, [StoreType.DOCUMENT]),
        ("postgres,redis,mongo", True, list(StoreType)),
        ("", True, []),
        ("postgres", False, []),
    ],
)
def test_store_types_follow_configuration_without_crd_access(monkeypatch, stores, datalab, expected):
    monkeypatch.setattr(config, "STORES", stores)

    def forbidden() -> None:
        pytest.fail("CRD definitions must not be read")

    monkeypatch.setattr(views.k8s_client, "ApiextensionsV1Api", forbidden)
    assert _available_store_types(datalab) == expected


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


@pytest.mark.parametrize("stores", ["database", "databases/mysql", "cacheStores/mongo"])
def test_invalid_store_configuration_reports_error(monkeypatch, stores):
    monkeypatch.setattr(config, "STORES", stores)
    with pytest.raises(ValueError, match="STORES must contain"):
        _available_store_types(True)


def test_store_configuration_accepts_case_and_duplicates(monkeypatch):
    monkeypatch.setattr(config, "STORES", " Mongo,mongo,REDIS ")
    assert _available_store_types(True) == [StoreType.CACHE, StoreType.DOCUMENT]
