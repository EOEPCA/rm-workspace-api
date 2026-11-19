# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from workspace_api import config, views
from workspace_api.models import StoreType
from workspace_api.tests.test_views import _dev_token, _overview_data
from workspace_api.views import _res_optional


def _environment_resources() -> SimpleNamespace:
    environments: dict[str, dict[str, Any]] = {
        name: {"metadata": {"name": name, "labels": labels}, "data": {"internal_setting": "private-test-value"}}
        for name, labels in (
            ("storage-minio", {"storages.pkg.internal/name": "minio"}),
            ("storage-project", {"storages.pkg.internal/name": ""}),
            ("datalab-educates", {"datalabs.pkg.internal/name": "educates"}),
            ("datalab-project", {"datalabs.pkg.internal/name": ""}),
            ("shared-project", {"storages.pkg.internal/name": "", "datalabs.pkg.internal/name": ""}),
            ("unlabeled", {}),
        )
    }
    compositions = {
        name: {
            "metadata": {"name": name, "labels": {"provider": backend}},
            "spec": {"compositeTypeRef": {"apiVersion": api_version, "kind": kind}},
        }
        for name, backend, api_version, kind in (
            ("storage-minio", "minio", views.API_STORAGE, views.KIND_STORAGE),
            ("datalab-educates", "educates", views.API_DATALAB, views.KIND_DATALAB),
        )
    }
    environment_api = mock.Mock()
    composition_api = mock.Mock()

    def environment_get(*, name=None, label_selector=None) -> Any:
        if name is None:
            return SimpleNamespace(
                items=[item for item in environments.values() if label_selector is None or label_selector in item["metadata"]["labels"]]
            )
        if name not in environments:
            raise ApiException(status=404)
        return environments[name]

    def composition_get(*, name=None) -> Any:
        if name is None:
            return SimpleNamespace(items=list(compositions.values()))
        if name not in compositions:
            raise ApiException(status=404)
        return compositions[name]

    environment_api.get.side_effect = environment_get
    composition_api.get.side_effect = composition_get
    return SimpleNamespace(
        environments=environments, compositions=compositions, environment_api=environment_api, composition_api=composition_api
    )


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
        environment = _environment_resources()
        environments = environment.environments
        compositions = environment.compositions
        environment_api = environment.environment_api
        composition_api = environment.composition_api
        resources = {**apis, views.KIND_ENVIRONMENT: environment_api, views.KIND_COMPOSITION: composition_api}
        discovery = mock.Mock(side_effect=lambda _api, kind: resources[kind])
        monkeypatch.setattr(views, "_res_optional", discovery)
        monkeypatch.setattr(views, "_available_store_types", lambda installed: [StoreType.DATABASE] if installed else [])
        return SimpleNamespace(
            apis=apis,
            discovery=discovery,
            resources=resources,
            environments=environments,
            compositions=compositions,
            environment_api=environment_api,
            composition_api=composition_api,
        )

    monkeypatch.setattr(views, "current_namespace", lambda: "workspace")
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    return configure


def headers(role: str = "admin") -> dict[str, str]:
    access = {"workspace-api": {"roles": ["admin"]}} if role == "admin" else {"ws-alice": {"roles": [role]}}
    return {"Authorization": f"Bearer {_dev_token(access)}"}


def _create_payload() -> dict[str, Any]:
    return {
        "preferred_name": "alice",
        "default_owner": "alice",
        "storage": {"composition": "storage-minio"},
        "datalab": {"composition": "datalab-educates"},
    }


@pytest.mark.parametrize("storage, datalab", [("absent", "present"), ("missing", "present"), ("present", "absent"), ("present", "missing")])
def test_workspace_works_with_one_resource(client: TestClient, providers, storage: str, datalab: str) -> None:
    providers(storage, datalab)
    response = client.get("/status", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"ok": True, "storage_enabled": True, "datalab_enabled": True}

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
    assert client.post("/workspaces", json=_create_payload(), headers=headers()).status_code == 503


@pytest.mark.parametrize("storage, datalab", [("absent", "missing"), ("missing", "absent")])
def test_create_workspace_uses_installed_providers(client: TestClient, providers, storage: str, datalab: str) -> None:
    setup = providers(storage, datalab)
    response = client.post("/workspaces", json=_create_payload(), headers=headers())
    assert response.status_code == 201
    for api in setup.apis.values():
        if api is not None:
            assert api.create.call_count == 1


def test_create_rejects_existing_datalab_without_creating_storage(client: TestClient, providers) -> None:
    setup = providers("missing", "present")
    response = client.post("/workspaces", json=_create_payload(), headers=headers())
    assert response.status_code == 422
    for api in setup.apis.values():
        api.create.assert_not_called()


@pytest.mark.parametrize(
    "storage_override, datalab_override",
    [
        (None, None),
        ("storage-project", None),
        (None, "datalab-project"),
        ("storage-project", "datalab-project"),
        ("shared-project", "shared-project"),
    ],
)
def test_workspace_uses_selected_compositions_and_optional_overrides(
    client: TestClient, providers, storage_override: str | None, datalab_override: str | None
) -> None:
    setup = providers("missing", "missing")
    payload = _create_payload()
    if storage_override:
        payload["storage"]["environment_name"] = storage_override
    if datalab_override:
        payload["datalab"]["environment_name"] = datalab_override
    response = client.post("/workspaces", json=payload, headers=headers())
    assert response.status_code == 201
    for kind, composition, override in (
        (views.KIND_STORAGE, "storage-minio", storage_override),
        (views.KIND_DATALAB, "datalab-educates", datalab_override),
    ):
        resource = setup.apis[kind].create.call_args.args[0]
        assert resource["spec"]["crossplane"]["compositionRef"] == {"name": composition}
        assert "annotations" not in resource["metadata"]
        if override:
            assert resource["spec"]["environmentName"] == override
        else:
            assert "environmentName" not in resource["spec"]
        assert setup.apis[kind].create.call_args.kwargs["query_params"] == [("fieldValidation", "Strict")]


def test_cloudferro_creation_keeps_the_selector_required_by_installed_scripts(client: TestClient, providers) -> None:
    setup = providers("missing", "absent")
    setup.compositions["regional-storage"] = deepcopy(setup.compositions["storage-minio"])
    setup.compositions["regional-storage"]["metadata"] = {"name": "regional-storage", "labels": {"provider": "cloudferro"}}
    payload = _create_payload()
    payload["storage"] = {"composition": "regional-storage"}
    response = client.post("/workspaces", json=payload, headers=headers())
    assert response.status_code == 201
    resource = setup.apis[views.KIND_STORAGE].create.call_args.args[0]
    assert resource["metadata"]["labels"] == {"storages.pkg.internal/backend": "cloudferro"}
    assert resource["spec"]["crossplane"] == {
        "compositionRef": {"name": "regional-storage"},
        "compositionSelector": {"matchLabels": {"provider": "cloudferro"}},
    }


@pytest.mark.parametrize(
    "failure",
    ["missing", "unknown-composition", "wrong-kind", "unlabeled", "wrong-provider", "unknown-config", "default-config", "forbidden"],
)
def test_selection_errors_create_no_workspace_resources(client: TestClient, providers, failure: str) -> None:
    setup = providers("missing", "missing")
    payload = _create_payload()
    if failure == "missing":
        del payload["datalab"]
    elif failure == "unknown-composition":
        payload["datalab"]["composition"] = "missing"
    elif failure == "wrong-kind":
        payload["datalab"]["composition"] = "storage-minio"
    elif failure == "unlabeled":
        payload["datalab"]["environment_name"] = "unlabeled"
    elif failure == "wrong-provider":
        payload["datalab"]["environment_name"] = "storage-project"
    elif failure == "unknown-config":
        payload["datalab"]["environment_name"] = "missing"
    elif failure == "default-config":
        payload["datalab"]["environment_name"] = "datalab-educates"
    else:
        setup.composition_api.get.side_effect = ApiException(status=403)
    response = client.post("/workspaces", json=payload, headers=headers())
    assert response.status_code == (503 if failure == "forbidden" else 422)
    for api in setup.apis.values():
        api.create.assert_not_called()


@pytest.mark.parametrize(
    "provider, composition, expected",
    [
        ("storage", "storage-minio", ["shared-project", "storage-project"]),
        ("datalab", "datalab-educates", ["datalab-project", "shared-project"]),
    ],
)
def test_override_choices_use_each_provider_label_and_exclude_composition_defaults(
    client: TestClient, providers, provider: str, composition: str, expected: list[str]
) -> None:
    providers("missing", "missing")
    response = client.get("/environments", params={"provider": provider, "composition": composition}, headers=headers())
    assert response.status_code == 200
    assert response.json() == expected
    assert "private-test-value" not in response.text


@pytest.mark.parametrize("length, expected", [(63, 201), (64, 422)])
def test_override_names_match_provider_length_limit(client: TestClient, providers, length: int, expected: int) -> None:
    setup = providers("missing", "missing")
    name = "a" * length
    setup.environments[name] = {"metadata": {"name": name, "labels": {"storages.pkg.internal/name": name}}}
    payload = _create_payload()
    payload["storage"]["environment_name"] = name
    response = client.post("/workspaces", json=payload, headers=headers())
    assert response.status_code == expected
    if expected == 201:
        assert setup.apis[views.KIND_STORAGE].create.call_args.args[0]["spec"]["environmentName"] == name
    else:
        assert response.json()["detail"][0]["loc"] == ["body", "storage", "environment_name"]
        for api in setup.apis.values():
            api.create.assert_not_called()


def test_composition_discovery_uses_provider_resource_type(client: TestClient, providers) -> None:
    setup = providers("missing", "missing")
    setup.compositions["old-datalab"] = deepcopy(setup.compositions["datalab-educates"])
    setup.compositions["old-datalab"]["metadata"]["name"] = "old-datalab"
    setup.compositions["old-datalab"]["spec"]["compositeTypeRef"]["apiVersion"] = "pkg.internal/v1beta1"
    for provider, expected in (("storage", ["storage-minio"]), ("datalab", ["datalab-educates"])):
        response = client.get("/compositions", params={"provider": provider}, headers=headers())
        assert response.status_code == 200
        assert response.json() == {"available": True, "compositions": expected}


def test_environment_listing_reports_missing_cluster_permissions(client: TestClient, providers) -> None:
    setup = providers("missing", "missing")
    setup.environment_api.get.side_effect = ApiException(status=403)
    response = client.get("/environments?provider=storage&composition=storage-minio", headers=headers())
    assert response.status_code == 503
    assert response.json()["detail"] == "Cannot list EnvironmentConfig resources"


@pytest.mark.parametrize("role", ["ws_admin", "ws_access", "ws_api"])
def test_workspace_lifecycle_requires_api_admin_before_cluster_access(client: TestClient, providers, role: str) -> None:
    setup = providers("present", "present")
    assert client.get("/compositions?provider=storage", headers=headers(role)).status_code == 403
    assert client.get("/environments?provider=storage&composition=storage-minio", headers=headers(role)).status_code == 403
    assert client.post("/workspaces", json={"preferred_name": "alice"}, headers=headers(role)).status_code == 403
    assert client.delete("/workspaces/ws-alice", headers=headers(role)).status_code == 403
    setup.discovery.assert_not_called()


@pytest.mark.parametrize("admin", [True, False])
def test_workspace_list_passes_admin_access_and_name_prefix_to_ui(
    client: TestClient, providers, admin: bool, ui_templates, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers("present", "present")
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "team-")
    response = client.get("/workspaces", headers={**headers("admin" if admin else "ws_admin"), "Accept": "text/html"})
    assert response.status_code == 200
    overview = _overview_data(response.text)
    assert overview["is_admin"] is admin
    assert overview["workspace_name_prefix"] == "team-"
    assert overview["compositions_url"] == "/compositions"
    assert overview["environments_url"] == "/environments"


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
    discovery = mock.Mock()
    discovery.resources.get.side_effect = lambda *, kind, **_kwargs: setup.resources[kind]
    monkeypatch.setattr(views, "_dyn", lambda: discovery)
    crd_api = mock.Mock()
    monkeypatch.setattr(views.k8s_client, "ApiextensionsV1Api", lambda: crd_api)

    response = client.get("/status", headers=headers())
    assert response.json() == {
        "ok": True,
        "storage_enabled": not disable_storage,
        "datalab_enabled": not disable_datalab,
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
    response = client.post("/workspaces", json=_create_payload(), headers=headers())
    assert response.status_code == (503 if both_disabled else 201)

    crd_api.read_custom_resource_definition.assert_not_called()
    for kind, disabled in (
        (views.KIND_STORAGE, disable_storage),
        (views.KIND_DATALAB, disable_datalab),
    ):
        if disabled:
            assert setup.apis[kind].mock_calls == []
            assert all(call.kwargs["kind"] != kind for call in discovery.resources.get.call_args_list)
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
