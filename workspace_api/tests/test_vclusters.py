# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from workspace_api import views
from workspace_api.tests.test_views import _dev_token


@pytest.fixture
def vcluster_api(monkeypatch: pytest.MonkeyPatch):
    api = mock.MagicMock()
    api.get.return_value = SimpleNamespace(
        spec={
            "vclusters": {
                "vc0": {
                    "groups": [
                        {"name": "namespace-demo", "namespace": "demo", "role": "view"},
                        {"name": "cluster-admin", "namespace": "*", "role": "cluster-admin"},
                    ],
                    "secretBindings": [{"type": "postgres", "name": "pg0", "target": {"namespace": "demo", "name": "database"}}],
                    "storage": "5Gi",
                },
                "vc1": {},
            },
            "users": ["alice"],
        },
        status={},
    )
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: api if kind == views.KIND_DATALAB else None)
    monkeypatch.setattr(views, "_available_store_types", lambda _available: [])
    monkeypatch.setattr(views, "current_namespace", lambda: "workspace")
    return api


def _headers(role: str = "ws_admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {_dev_token({'ws-alice': {'roles': [role]}})}"}


@pytest.mark.parametrize("role, visible", [("ws_admin", True), ("ws_access", True), ("ws_api", False)])
def test_workspace_lists_configured_additional_vcluster_groups(client: TestClient, vcluster_api, role: str, visible: bool) -> None:
    response = client.get("/workspaces/ws-alice?view=management", headers=_headers(role))
    assert response.status_code == 200
    assert response.json()["datalab"]["vclusters"] == (
        [
            {"name": "vc0", "groups": [{"name": "namespace-demo", "namespace": "demo", "role": "view"}]},
            {"name": "vc1", "groups": []},
        ]
        if visible
        else []
    )


@pytest.mark.parametrize("role", ["view", "edit", "admin"])
def test_add_group_preserves_existing_profiles_bindings_and_cluster_settings(client: TestClient, vcluster_api, role: str) -> None:
    original = deepcopy(vcluster_api.get.return_value.spec)
    response = client.post(
        "/workspaces/ws-alice/vclusters/vc0/groups",
        json={"name": "team-analysis", "namespace": "analysis", "role": role},
        headers=_headers(),
    )
    assert response.status_code == 201
    group = {"name": "team-analysis", "namespace": "analysis", "role": role}
    assert response.json() == group
    patch = vcluster_api.patch.call_args.kwargs
    assert patch["content_type"] == "application/json-patch+json"
    assert patch["body"] == [
        {"op": "test", "path": "/spec/vclusters/vc0", "value": original["vclusters"]["vc0"]},
        {"op": "add", "path": "/spec/vclusters/vc0/groups", "value": [*original["vclusters"]["vc0"]["groups"], group]},
    ]
    assert vcluster_api.get.return_value.spec == original


@pytest.mark.parametrize(
    "namespace", ["kube-system", "kubefoo", "default", "*", "Upper", "a.b", "a_1", "-demo", "demo-", "1demo", "a" * 64]
)
def test_group_creation_rejects_invalid_or_reserved_namespaces(client: TestClient, vcluster_api, namespace: str) -> None:
    response = client.post("/workspaces/ws-alice/vclusters/vc0/groups", json={"namespace": namespace, "role": "edit"}, headers=_headers())
    assert response.status_code == 422
    vcluster_api.patch.assert_not_called()


@pytest.mark.parametrize("role", ["cluster-admin", "unknown"])
def test_group_creation_rejects_non_namespace_roles(client: TestClient, vcluster_api, role: str) -> None:
    response = client.post("/workspaces/ws-alice/vclusters/vc0/groups", json={"namespace": "analysis", "role": role}, headers=_headers())
    assert response.status_code == 422
    vcluster_api.patch.assert_not_called()


@pytest.mark.parametrize("role", ["ws_access", "ws_api"])
def test_only_workspace_admins_can_add_groups(client: TestClient, vcluster_api, role: str) -> None:
    response = client.post(
        "/workspaces/ws-alice/vclusters/vc0/groups", json={"namespace": "analysis", "role": "edit"}, headers=_headers(role)
    )
    assert response.status_code == 403
    vcluster_api.get.assert_not_called()
    vcluster_api.patch.assert_not_called()


def test_group_creation_handles_empty_group_list_and_long_namespace(client: TestClient, vcluster_api) -> None:
    response = client.post("/workspaces/ws-alice/vclusters/vc1/groups", json={"namespace": "a" * 63, "role": "edit"}, headers=_headers())
    assert response.status_code == 201
    assert len(response.json()["name"]) <= 40
    assert response.json()["namespace"] == "a" * 63
    assert vcluster_api.patch.call_args.kwargs["body"][1]["path"] == "/spec/vclusters/vc1/groups"


@pytest.mark.parametrize("name", ["namespace-demo", "cluster-admin"])
def test_group_creation_rejects_duplicate_or_reserved_group_name(client: TestClient, vcluster_api, name: str) -> None:
    response = client.post(
        "/workspaces/ws-alice/vclusters/vc0/groups", json={"name": name, "namespace": "analysis", "role": "edit"}, headers=_headers()
    )
    assert response.status_code == 409
    vcluster_api.patch.assert_not_called()


def test_group_creation_rejects_unknown_instance(client: TestClient, vcluster_api) -> None:
    response = client.post("/workspaces/ws-alice/vclusters/vc9/groups", json={"namespace": "analysis", "role": "edit"}, headers=_headers())
    assert response.status_code == 404
    vcluster_api.patch.assert_not_called()


def test_group_creation_reports_concurrent_configuration_change(client: TestClient, vcluster_api) -> None:
    vcluster_api.patch.side_effect = ApiException(status=422)
    response = client.post("/workspaces/ws-alice/vclusters/vc0/groups", json={"namespace": "analysis", "role": "edit"}, headers=_headers())
    assert response.status_code == 409


def test_removed_vector_store_type_is_rejected(client: TestClient, vcluster_api) -> None:
    response = client.put("/workspaces/ws-alice", json={"add_stores": [{"name": "legacy", "type": "vector"}]}, headers=_headers())
    assert response.status_code == 422
    vcluster_api.patch.assert_not_called()


def test_normal_workspace_uses_published_vcluster_profiles(client: TestClient, vcluster_api) -> None:
    vcluster_api.get.return_value.status = {
        "connections": [
            {
                "type": "vcluster",
                "name": "vc0-admin",
                "instance": "vc0",
                "group": "cluster-admin",
                "targetNamespace": "*",
                "role": "cluster-admin",
                "ready": False,
            },
            {
                "type": "vcluster",
                "name": "vc2-editors",
                "instance": "vc2",
                "group": "editors",
                "targetNamespace": "analysis",
                "role": "edit",
                "ready": False,
            },
        ]
    }
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=_headers())
    assert response.status_code == 200
    assert response.json()["datalab"]["vclusters"] == [
        {"name": "vc0", "groups": []},
        {"name": "vc2", "groups": [{"name": "editors", "namespace": "analysis", "role": "edit", "ready": False}]},
    ]
    vcluster_api.get.return_value.status = {}
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=_headers())
    assert response.json()["datalab"]["vclusters"] == []
