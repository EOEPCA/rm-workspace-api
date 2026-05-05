# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from http import HTTPStatus
from unittest import mock

from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from workspace_api import config, views
from workspace_api.views import _initial_sessions_for_mode, _sessions_with_state


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


def test_sessions_with_state_preserves_existing_object_fields() -> None:
    updated = _sessions_with_state(
        [
            "legacy",
            {"name": "default", "state": "stopped", "extra": "kept"},
        ],
        "default",
        "started",
    )

    assert updated == [
        {"name": "legacy", "state": "started"},
        {"name": "default", "state": "started", "extra": "kept"},
    ]


def test_create_workspace_sends_started_session_object(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "PREFIX_FOR_NAME", "")
    monkeypatch.setattr(config, "SESSION_MODE", "on")
    monkeypatch.setattr(config, "USE_VCLUSTER", "false")

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
    assert created["spec"]["sessions"] == [{"name": "default", "state": "started"}]


def test_auto_session_request_starts_stopped_session_object(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
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
    assert datalab_api.patch.call_args.kwargs["body"] == {
        "spec": {"sessions": [{"name": "default", "state": "started"}]},
    }


def test_started_session_object_returns_status_url(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "SESSION_MODE", "auto")
    datalab_api = mock.MagicMock()
    datalab = mock.MagicMock()
    datalab.spec = {"sessions": [{"name": "default", "state": "started"}]}
    datalab.status = {"sessions": {"default": {"state": "started", "url": "https://session.example"}}}

    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)

    response = client.get(
        "/workspaces/workspace-a/sessions/default",
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"url": "https://session.example"}
    datalab_api.patch.assert_not_called()
