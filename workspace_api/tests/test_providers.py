# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from workspace_api import config, views
from workspace_api.models import StoreType
from workspace_api.tests.test_views import _dev_token
from workspace_api.views import _crd_exists, _res_optional


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch):
    def configure(storage: str, datalab: str) -> SimpleNamespace:
        apis: dict[str, mock.Mock | None] = {}
        for kind, state in ((views.KIND_STORAGE, storage), (views.KIND_DATALAB, datalab)):
            if state == "absent":
                apis[kind] = None
                continue
            resource = SimpleNamespace(
                metadata=SimpleNamespace(name="ws-alice", creationTimestamp=None, resourceVersion="1"),
                spec={"principal": "ws-alice", "buckets": []} if kind == views.KIND_STORAGE else {"users": ["alice"], "sessions": []},
                status={"conditions": [{"type": "Ready", "status": "True"}]},
            )
            api = mock.Mock()

            def get(*, name=None, namespace=None, item=resource, exists=state == "present") -> SimpleNamespace:
                if name is None:
                    return SimpleNamespace(items=[item] if exists else [])
                if not exists:
                    raise ApiException(status=404)
                return item

            api.get.side_effect = get
            if state != "present":
                api.delete.side_effect = ApiException(status=404)
            apis[kind] = api
        discovery = mock.Mock(side_effect=lambda _api, kind: apis[kind])
        monkeypatch.setattr(views, "_res_optional", discovery)
        monkeypatch.setattr(
            views, "_crd_exists", lambda name: apis[views.KIND_STORAGE if name == views.CRD_STORAGE else views.KIND_DATALAB] is not None
        )
        monkeypatch.setattr(views, "_available_store_types", lambda installed: [StoreType.DATABASE] if installed else [])
        return SimpleNamespace(apis=apis, discovery=discovery)

    monkeypatch.setattr(views, "current_namespace", lambda: "workspace")
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    return configure


def headers(role: str = "admin") -> dict[str, str]:
    access = {"workspace-api": {"roles": ["admin"]}} if role == "admin" else {"ws-alice": {"roles": [role]}}
    return {"Authorization": f"Bearer {_dev_token(access)}"}


@pytest.mark.parametrize("storage, datalab", [("absent", "present"), ("missing", "present"), ("present", "absent"), ("present", "missing")])
def test_workspace_works_with_one_resource(client: TestClient, providers, storage: str, datalab: str) -> None:
    providers(storage, datalab)
    response = client.get("/status", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"ok": True, "storage_crd_present": storage != "absent", "datalab_crd_present": datalab != "absent"}

    response = client.get("/workspaces/ws-alice", headers=headers())
    assert response.status_code == 200
    data = response.json()
    assert data["storage"]["available"] is (storage == "present")
    assert data["datalab"]["available"] is (datalab == "present")
    assert data["version"] == "1"
    assert data["status"] == "ready"
    assert [workspace["name"] for workspace in client.get("/workspaces", headers=headers()).json()] == ["ws-alice"]
    assert client.delete("/workspaces/ws-alice", headers=headers()).status_code == 204


def test_cluster_without_workspace_providers(client: TestClient, providers) -> None:
    providers("absent", "absent")
    assert client.get("/status", headers=headers()).json()["ok"] is True
    assert client.get("/workspaces", headers=headers()).json() == []
    assert client.get("/workspaces/ws-alice", headers=headers()).status_code == 404
    assert client.delete("/workspaces/ws-alice", headers=headers()).status_code == 404
    assert client.post("/workspaces", json={"preferred_name": "alice", "default_owner": "alice"}, headers=headers()).status_code == 503


@pytest.mark.parametrize("storage, datalab", [("missing", "missing"), ("absent", "missing"), ("missing", "absent")])
def test_create_workspace_uses_installed_providers(client: TestClient, providers, storage: str, datalab: str) -> None:
    setup = providers(storage, datalab)
    response = client.post("/workspaces", json={"preferred_name": "alice", "default_owner": "alice"}, headers=headers())
    assert response.status_code == 201
    for api in setup.apis.values():
        if api is not None:
            assert api.create.call_count == 1


def test_create_rejects_existing_datalab_without_creating_storage(client: TestClient, providers) -> None:
    setup = providers("missing", "present")
    response = client.post("/workspaces", json={"preferred_name": "alice", "default_owner": "alice"}, headers=headers())
    assert response.status_code == 422
    for api in setup.apis.values():
        api.create.assert_not_called()


def test_datalab_updates_do_not_use_storage(client: TestClient, providers) -> None:
    setup = providers("absent", "present")
    response = client.put(
        "/workspaces/ws-alice",
        json={
            "add_memberships": [{"member": "bob", "role": "user"}],
            "add_stores": [{"name": "analytics", "type": "database"}],
        },
        headers=headers(),
    )
    assert response.status_code == 202
    spec = setup.apis[views.KIND_DATALAB].patch.call_args.kwargs["body"]["spec"]
    assert spec["users"] == ["alice", "bob"]
    assert spec["databases"]["pg0"]["names"] == ["analytics"]
    assert all(call.args[1] == views.KIND_DATALAB for call in setup.discovery.call_args_list)


@pytest.mark.parametrize("kind", [views.KIND_STORAGE, views.KIND_DATALAB])
@pytest.mark.parametrize("state, expected", [("absent", 503), ("missing", 404)])
def test_updates_require_the_target_resource(client: TestClient, providers, kind: str, state: str, expected: int) -> None:
    setup = providers(state if kind == views.KIND_STORAGE else "present", state if kind == views.KIND_DATALAB else "present")
    update = (
        {"add_buckets": [{"name": "observations"}]}
        if kind == views.KIND_STORAGE
        else {"add_memberships": [{"member": "bob", "role": "user"}]}
    )
    response = client.put("/workspaces/ws-alice", json=update, headers=headers())
    assert response.status_code == expected
    for api in setup.apis.values():
        if api is not None:
            api.patch.assert_not_called()


def test_bucket_access_changes_require_management_permission(client: TestClient, providers) -> None:
    setup = providers("present", "absent")
    response = client.put(
        "/workspaces/ws-alice",
        json={
            "patch_bucket_access_requests": [
                {
                    "workspace": "ws-alice",
                    "bucket": "observations",
                    "permission": "ReadOnly",
                    "request_timestamp": "2026-11-04T10:00:00Z",
                }
            ]
        },
        headers=headers("ws_access"),
    )
    assert response.status_code == 403
    setup.discovery.assert_not_called()


def test_optional_discovery_keeps_access_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = mock.Mock()
    monkeypatch.setattr(views, "_dyn", lambda: discovery)
    discovery.resources.get.side_effect = ResourceNotFoundError
    assert _res_optional(views.API_STORAGE, views.KIND_STORAGE) is None

    discovery.resources.get.side_effect = ApiException(status=403)
    with pytest.raises(ApiException) as error:
        _res_optional(views.API_STORAGE, views.KIND_STORAGE)
    assert error.value.status == 403


@pytest.mark.parametrize("disable_storage, disable_datalab", [(True, False), (False, True), (True, True)])
def test_disabled_providers_skip_cluster_access(
    client: TestClient, providers, monkeypatch: pytest.MonkeyPatch, disable_storage: bool, disable_datalab: bool
) -> None:
    setup = providers("present", "present")
    monkeypatch.setattr(config, "DISABLE_STORAGE", str(disable_storage).lower())
    monkeypatch.setattr(config, "DISABLE_DATALAB", str(disable_datalab).lower())
    monkeypatch.setattr(views, "_res_optional", _res_optional)
    monkeypatch.setattr(views, "_crd_exists", _crd_exists)
    discovery = mock.Mock()
    discovery.resources.get.side_effect = lambda *, kind, **_kwargs: setup.apis[kind]
    monkeypatch.setattr(views, "_dyn", lambda: discovery)
    crd_api = mock.Mock()
    monkeypatch.setattr(views.k8s_client, "ApiextensionsV1Api", lambda: crd_api)

    response = client.get("/status", headers=headers())
    assert response.json() == {
        "ok": True,
        "storage_crd_present": not disable_storage,
        "datalab_crd_present": not disable_datalab,
    }
    both_disabled = disable_storage and disable_datalab
    response = client.get("/workspaces/ws-alice", headers=headers())
    assert response.status_code == (404 if both_disabled else 200)
    if not both_disabled:
        assert response.json()["storage"]["available"] is not disable_storage
        assert response.json()["datalab"]["available"] is not disable_datalab
    response = client.get("/workspaces", headers=headers())
    assert [workspace["name"] for workspace in response.json()] == ([] if both_disabled else ["ws-alice"])

    for kind, disabled, update in (
        (views.KIND_STORAGE, disable_storage, {"add_buckets": [{"name": "observations"}]}),
        (views.KIND_DATALAB, disable_datalab, {"add_memberships": [{"member": "bob", "role": "user"}]}),
    ):
        if disabled:
            assert client.put("/workspaces/ws-alice", json=update, headers=headers()).status_code == 503
            if kind == views.KIND_DATALAB:
                response = client.patch("/workspaces/ws-alice/sessions/default", json={"state": "started"}, headers=headers())
                assert response.status_code == 503

    assert client.delete("/workspaces/ws-alice", headers=headers()).status_code == (404 if both_disabled else 204)
    for api in setup.apis.values():
        api.get.side_effect = ApiException(status=404)
    response = client.post("/workspaces", json={"preferred_name": "alice", "default_owner": "alice"}, headers=headers())
    assert response.status_code == (503 if both_disabled else 201)

    for kind, disabled, crd in (
        (views.KIND_STORAGE, disable_storage, views.CRD_STORAGE),
        (views.KIND_DATALAB, disable_datalab, views.CRD_DATALAB),
    ):
        if disabled:
            assert setup.apis[kind].mock_calls == []
            assert all(call.kwargs["kind"] != kind for call in discovery.resources.get.call_args_list)
            assert mock.call(crd) not in crd_api.read_custom_resource_definition.call_args_list
        else:
            setup.apis[kind].create.assert_called_once()


@pytest.mark.parametrize("failure", ["resource", "sync", "connection"])
def test_workspace_ready_requires_all_published_resources(client: TestClient, providers, failure: str) -> None:
    setup = providers("present", "present")
    datalab = setup.apis[views.KIND_DATALAB].get(name="ws-alice", namespace="workspace")
    if failure == "resource":
        datalab.status["conditions"] = [{"type": "Ready", "status": "False"}]
    elif failure == "sync":
        datalab.status["conditions"].append({"type": "Synced", "status": "False"})
    else:
        datalab.status["connections"] = [
            {"name": "cache", "type": "redis", "ready": False, "secretRef": {"name": "cache", "namespace": "workspace"}}
        ]
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=headers())
    assert response.status_code == 200
    assert response.json()["status"] == "provisioning"
