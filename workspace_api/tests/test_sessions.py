# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from http import HTTPStatus
from unittest import mock

from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from workspace_api import config, views
from workspace_api.views import (
    _datalab_declares_session,
    _initial_sessions_for_mode,
    _session_probe_url,
    _session_start_patch,
    _session_url_ready,
)


def _dev_token() -> str:
    def enc(obj: object) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = enc({"alg": "none", "typ": "JWT"})
    payload = enc(
        {
            "preferred_username": "test",
            "resource_access": {"workspace-api": {"roles": ["admin"]}},
        }
    )
    return f"{header}.{payload}."


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_dev_token()}"}


def test_initial_sessions_use_provider_datalab_v1beta2_shape() -> None:
    assert _initial_sessions_for_mode("on") == [{"name": "default", "state": "started"}]
    assert _initial_sessions_for_mode("auto") == [{"name": "default", "state": "stopped"}]
    assert _initial_sessions_for_mode("off") == []


def test_session_start_patch_only_touches_default_session() -> None:
    patch = _session_start_patch(
        [
            "legacy",
            {"name": "default", "state": "stopped", "extra": "kept"},
        ],
        "default",
    )

    assert patch == [{"op": "replace", "path": "/spec/sessions/1/state", "value": "started"}]


def test_session_start_patch_replaces_legacy_default_session() -> None:
    assert _session_start_patch(["default"], "default") == [
        {"op": "replace", "path": "/spec/sessions/0", "value": {"name": "default", "state": "started"}}
    ]


def test_session_probe_url_uses_internal_session_service() -> None:
    assert _session_probe_url("workspace-a", "default") == "http://workspace-a-default.workspace-a.svc.cluster.local/"


def test_create_workspace_sends_started_session_object(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "PROVIDER_ENVIRONMENT", "datalab")
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")
    monkeypatch.setattr(config, "DISABLE_DOCKER_REGISTRY", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created_storage = storage_api.create.call_args.args[0]
    created = datalab_api.create.call_args.args[0]
    assert created_storage["metadata"]["annotations"] == {"storages.pkg.internal/environment": "datalab"}
    assert created["metadata"]["annotations"] == {"datalabs.pkg.internal/environment": "datalab"}
    assert created["spec"]["sessions"] == [{"name": "default", "state": "started"}]
    assert created["spec"]["registry"] == {"enabled": True}


def test_create_workspace_uses_configured_provider_environment(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "PROVIDER_ENVIRONMENT", "demo")
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")
    monkeypatch.setattr(config, "DISABLE_DOCKER_REGISTRY", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created_storage = storage_api.create.call_args.args[0]
    created_datalab = datalab_api.create.call_args.args[0]
    assert created_storage["metadata"]["annotations"] == {"storages.pkg.internal/environment": "demo"}
    assert created_datalab["metadata"]["annotations"] == {"datalabs.pkg.internal/environment": "demo"}


def test_create_workspace_sends_stopped_default_session_in_auto_mode(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")
    monkeypatch.setattr(config, "DISABLE_DOCKER_REGISTRY", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

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
    monkeypatch.setattr(config, "DISABLE_DOCKER_REGISTRY", "false")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created = datalab_api.create.call_args.args[0]
    assert "sessions" not in created["spec"]


def test_create_workspace_can_disable_docker_registry(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")
    monkeypatch.setattr(config, "DISABLE_DOCKER_REGISTRY", "true")

    storage_api = mock.MagicMock()
    storage_api.get.side_effect = ApiException(status=HTTPStatus.NOT_FOUND)
    datalab_api = mock.MagicMock()

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.post(
        "/workspaces",
        json={"preferred_name": "Team Blue", "default_owner": "alice"},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    created = datalab_api.create.call_args.args[0]
    assert "registry" not in created["spec"]


def test_session_request_starts_stopped_session_object(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "off")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "stopped"}]}
    datalab.status = {"sessions": {"default": {"state": "stopped"}}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert datalab_api.patch.call_args.kwargs["body"] == [{"op": "replace", "path": "/spec/sessions/0/state", "value": "started"}]
    assert datalab_api.patch.call_args.kwargs["content_type"] == "application/json-patch+json"


def test_missing_session_request_does_not_create_default_session(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": []}
    datalab.status = {"sessions": {}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    datalab_api.patch.assert_not_called()


def test_non_default_session_request_is_not_managed(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.get(
        "/workspaces/workspace-a/sessions/other",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    datalab_api.patch.assert_not_called()
    datalab_api.get.assert_not_called()


def test_default_session_menu_visibility_uses_declared_sessions(monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "stopped"}]}
    datalab_api.get.return_value = datalab
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    assert _datalab_declares_session("workspace-a", "default") is True

    datalab.spec = {"sessions": [{"name": "other", "state": "started"}]}

    assert _datalab_declares_session("workspace-a", "default") is False
    assert _datalab_declares_session("workspace-a", "other") is False


def test_started_session_object_returns_status_url(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": {"default": {"state": "started", "url": "https://session.example"}}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)
    monkeypatch.setattr(views, "_session_url_ready", lambda _url: True)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"url": "https://session.example"}
    datalab_api.patch.assert_not_called()


def test_started_session_keeps_waiting_when_status_url_returns_503(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": {"default": {"state": "started", "url": "https://session.example"}}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)
    monkeypatch.setattr(views, "_session_url_ready", lambda _url: False)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json() == {"status": "starting", "url": "https://session.example"}
    datalab_api.patch.assert_not_called()


def test_session_url_ready_accepts_auth_redirect(requests_mock) -> None:
    requests_mock.head("https://session.example", status_code=HTTPStatus.FOUND, headers={"Location": "https://auth.example/start"})

    assert _session_url_ready("https://session.example") is True


def test_session_url_ready_waits_on_server_error(requests_mock) -> None:
    requests_mock.head("https://session.example", status_code=HTTPStatus.SERVICE_UNAVAILABLE)

    assert _session_url_ready("https://session.example") is False


def test_html_session_waiter_redirects_without_cross_origin_probe(client: TestClient, monkeypatch) -> None:
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": {"default": {"state": "started", "url": "https://session.example"}}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers={**_auth_headers(), "Accept": "text/html"},
    )

    assert response.status_code == HTTPStatus.OK
    assert "checked-url" in response.text
    assert "showUrl('Checking:', apiUrl)" in response.text
    assert "showUrl('Session URL:', url)" in response.text
    assert "showUrl('Session URL:', d.url)" in response.text
    assert "location.replace(url)" in response.text
    assert "fetch(url" not in response.text
    assert "method:'HEAD'" not in response.text
