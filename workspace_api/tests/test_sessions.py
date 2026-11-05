# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from workspace_api import config, views


def _dev_token() -> str:
    def enc(obj: object) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = enc({"alg": "none", "typ": "JWT"})
    payload = enc(
        {
            "aud": "workspace-api",
            "preferred_username": "test",
            "resource_access": {"workspace-api": {"roles": ["admin"]}},
        }
    )
    return f"{header}.{payload}."


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_dev_token()}"}


@pytest.mark.parametrize("use_vcluster, environment", [("false", "datalab"), ("true", "demo")])
def test_create_workspace_sends_started_session_object(client: TestClient, monkeypatch, use_vcluster: str, environment: str) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "PROVIDER_ENVIRONMENT", environment)
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "USE_VCLUSTER", use_vcluster)

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()
    datalab_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)

    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created_storage = storage_api.create.call_args.args[0]
    created = datalab_api.create.call_args.args[0]
    assert created_storage["metadata"]["annotations"] == {"storages.pkg.internal/environment": environment}
    assert created["metadata"]["annotations"] == {"datalabs.pkg.internal/environment": environment}
    assert created["spec"]["sessions"] == [{"name": "default", "state": "started"}]
    assert "registry" not in created["spec"]
    assert "secretName" not in created["spec"]
    assert "vcluster" not in created["spec"]
    if use_vcluster == "true":
        assert created["spec"]["vclusters"] == {"vc0": {}}
    else:
        assert "vclusters" not in created["spec"]


def test_create_workspace_sends_stopped_default_session_in_auto_mode(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()
    datalab_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)

    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created = datalab_api.create.call_args.args[0]
    assert created["spec"]["sessions"] == [{"name": "default", "state": "stopped"}]


def test_create_workspace_does_not_touch_sessions_in_off_mode(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "off")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()
    datalab_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)

    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created = datalab_api.create.call_args.args[0]
    assert "sessions" not in created["spec"]


def test_create_workspace_respects_zero_session_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "MAX_SESSIONS", "0")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()
    datalab_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)

    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created = datalab_api.create.call_args.args[0]
    assert "sessions" not in created["spec"]


def test_missing_session_request_does_not_create_default_session(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": []}
    datalab.status = {"sessions": []}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/ws-alice/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    datalab_api.patch.assert_not_called()


def test_non_default_session_request_starts_declared_session(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}, {"name": "analysis", "state": "stopped"}]}
    datalab.status = {"sessions": [{"name": "analysis", "state": "stopped"}]}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/ws-alice/sessions/analysis",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert datalab_api.patch.call_args.kwargs["body"] == [{"op": "replace", "path": "/spec/sessions/1/state", "value": "started"}]


def test_list_workspace_sessions_reads_published_list(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}, {"name": "analysis", "state": "stopped"}]}
    datalab.status = {
        "sessions": [
            {"name": "default", "state": "started", "phase": "Running", "url": "https://session.example"},
            {"name": "analysis", "state": "stopped", "phase": "Stopped"},
            {"name": "notebook", "state": "started", "phase": "Running", "url": "https://notebook.example"},
        ]
    }
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.get(
        "/workspaces/ws-alice/sessions",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {"name": "default", "state": "started", "url": "https://session.example", "ready": True, "phase": "Running"},
        {"name": "analysis", "state": "stopped", "ready": False, "phase": "Stopped"},
        {"name": "notebook", "state": "started", "url": "https://notebook.example", "ready": True, "phase": "Running"},
    ]


def test_create_workspace_session_appends_session(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_SESSIONS", "3")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": []}
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces/ws-alice/sessions",
        json={"name": "analysis", "state": "stopped"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {"name": "analysis", "state": "stopped", "ready": False}
    assert datalab_api.patch.call_args.kwargs["body"] == [
        {"op": "add", "path": "/spec/sessions/-", "value": {"name": "analysis", "state": "stopped"}}
    ]
    assert datalab_api.patch.call_args.kwargs["content_type"] == "application/json-patch+json"


def test_create_workspace_session_initializes_sessions_field(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_SESSIONS", "3")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {}
    datalab.status = {"sessions": []}
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces/ws-alice/sessions",
        json={"name": "analysis"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert datalab_api.patch.call_args.kwargs["body"] == [
        {"op": "add", "path": "/spec/sessions", "value": [{"name": "analysis", "state": "stopped"}]}
    ]


def test_create_workspace_session_rejects_session_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_SESSIONS", "3")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {
        "sessions": [
            {"name": "default", "state": "started"},
            {"name": "analysis", "state": "stopped"},
            {"name": "debug", "state": "stopped"},
        ]
    }
    datalab.status = {"sessions": []}
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces/ws-alice/sessions",
        json={"name": "extra"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == {"error": "session_limit_exceeded", "max_sessions": 3}
    datalab_api.patch.assert_not_called()


def test_update_workspace_session_state_stops_session(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": [{"name": "default", "state": "started", "phase": "Running", "url": "https://session.example"}]}
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.patch(
        "/workspaces/ws-alice/sessions/default",
        json={"state": "stopped"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json() == {"name": "default", "state": "stopped", "ready": False}
    assert datalab_api.patch.call_args.kwargs["body"] == [{"op": "replace", "path": "/spec/sessions/0/state", "value": "stopped"}]


def test_delete_workspace_session_removes_session(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}, {"name": "analysis", "state": "stopped"}]}
    datalab.status = {"sessions": []}
    datalab_api.get.return_value = datalab

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.delete(
        "/workspaces/ws-alice/sessions/analysis",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert datalab_api.patch.call_args.kwargs["body"] == [{"op": "remove", "path": "/spec/sessions/1"}]


@pytest.mark.parametrize("declared", [True, False])
def test_started_session_returns_published_url_without_probe(client: TestClient, monkeypatch, requests_mock, declared: bool) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}] if declared else []}
    datalab.status = {
        "sessions": [{"name": "default", "state": "started", "phase": "Running", "url": "https://session.example/custom-path"}]
    }

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/ws-alice/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"url": "https://session.example/custom-path"}
    assert not requests_mock.called
    datalab_api.patch.assert_not_called()


@pytest.mark.parametrize("state, phase", [("stopped", "Running"), ("started", "Pending"), ("started", None)])
def test_session_waits_for_published_runtime_state(client: TestClient, monkeypatch, requests_mock, state: str, phase: str | None) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": [{"name": "default", "state": state, "phase": phase, "url": "https://session.example"}]}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/ws-alice/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json() == {"status": "starting", "url": "https://session.example"}
    assert not requests_mock.called
    datalab_api.patch.assert_not_called()


@pytest.mark.parametrize("declaration", ["default", {"name": "default", "state": "invalid"}])
def test_invalid_session_declaration_is_not_started(client: TestClient, monkeypatch, declaration) -> None:
    datalab_api = mock.Mock()
    datalab = mock.Mock()
    datalab.spec = {"sessions": [declaration]}
    datalab.status = {"sessions": []}
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get("/workspaces/ws-alice/sessions/default", headers=_auth_headers())

    assert response.status_code == HTTPStatus.NOT_FOUND
    datalab_api.patch.assert_not_called()


def test_start_session_does_not_return_stale_ready_url(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.Mock()
    datalab = mock.Mock()
    datalab.spec = {"sessions": [{"name": "default", "state": "stopped"}]}
    datalab.status = {"sessions": [{"name": "default", "state": "stopped", "phase": "Pending", "url": "https://session.example"}]}
    datalab_api.get.return_value = datalab
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.patch("/workspaces/ws-alice/sessions/default", json={"state": "started"}, headers=_auth_headers())

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["ready"] is False
    assert datalab_api.patch.call_args.kwargs["body"] == [{"op": "replace", "path": "/spec/sessions/0/state", "value": "started"}]


@pytest.mark.parametrize("published", [True, False])
def test_browser_session_uses_only_published_url(client: TestClient, monkeypatch, published: bool) -> None:
    datalab = mock.Mock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    entry = {"name": "default", "state": "started", "phase": "Running"}
    if published:
        entry["url"] = "https://session.example/custom-path"
    datalab.status = {"sessions": [entry]}
    monkeypatch.setattr(views, "_res_optional", lambda *_args: mock.Mock())
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)
    response = client.get(
        "/workspaces/ws-alice/sessions/default", headers={**_auth_headers(), "Accept": "text/html"}, follow_redirects=False
    )
    if published:
        assert response.status_code == HTTPStatus.TEMPORARY_REDIRECT
        assert response.headers["location"] == entry["url"]
    else:
        assert response.status_code == HTTPStatus.ACCEPTED
        assert "location" not in response.headers
        assert "<script>" not in response.text


def test_session_reads_use_status_and_management_keeps_declarations(client: TestClient, monkeypatch) -> None:
    datalab = SimpleNamespace(
        spec={"sessions": [{"name": "default", "state": "started"}, {"name": "analysis", "state": "stopped"}]},
        status={"sessions": [{"name": "default", "state": "stopped", "phase": "Stopped", "message": "Runtime stopped"}]},
    )
    api = mock.Mock()
    api.get.return_value = datalab
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: api if kind == views.KIND_DATALAB else None)
    monkeypatch.setattr(views, "_available_store_types", lambda _installed: [])
    response = client.get("/workspaces/ws-alice/sessions", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json() == [{"name": "default", "state": "stopped", "phase": "Stopped", "message": "Runtime stopped", "ready": False}]
    management = client.get("/workspaces/ws-alice?view=management&resolve_connections=none", headers=_auth_headers())
    assert management.status_code == 200
    assert [(item["name"], item["state"], item["ready"]) for item in management.json()["datalab"]["sessions"]] == [
        ("default", "started", False),
        ("analysis", "stopped", False),
    ]
    datalab.status = {}
    assert client.get("/workspaces/ws-alice/sessions", headers=_auth_headers()).json() == []


@pytest.mark.parametrize("size, expected", [("10Gi", "10Gi"), ("1.5Gi", "1536Mi"), ("0", "0"), (None, None), ("invalid", None)])
def test_workspace_session_storage_uses_published_size_without_pvc_reads(client: TestClient, monkeypatch, size, expected) -> None:
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None),
        spec={"sessions": [{"name": "default", "state": "stopped"}]},
        status={"sessions": [{"name": "default", "state": "stopped", "pvcSize": size}]},
    )
    api = mock.Mock()
    api.get.return_value = datalab
    core_api = mock.Mock(side_effect=AssertionError("Session storage must come from Datalab status"))
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: api if kind == views.KIND_DATALAB else None)
    monkeypatch.setattr(views, "_available_store_types", lambda _installed: [])
    monkeypatch.setattr(views.k8s_client, "CoreV1Api", core_api)

    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=_auth_headers())

    assert response.status_code == HTTPStatus.OK
    session = response.json()["datalab"]["sessions"][0]
    assert session["state"] == "stopped"
    assert session.get("pvc_size") == expected
    assert "resource_usage" not in response.json()
    core_api.assert_not_called()
