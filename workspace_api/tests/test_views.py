# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from collections.abc import Generator
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes import client as k8s_client  # type: ignore[import-untyped]

from workspace_api import views


def _dev_token(
    resource_access: dict[str, dict[str, list[str]]] | None = None,
    audience: str | list[str] | None = "workspace-api",
) -> str:
    def enc(obj: object) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    if resource_access is None:
        resource_access = {"workspace-api": {"roles": ["admin"]}}

    header = enc({"alg": "none", "typ": "JWT"})
    claims: dict[str, object] = {
        "preferred_username": "test",
        "resource_access": resource_access,
    }
    if audience is not None:
        claims["aud"] = audience

    payload = enc(claims)
    return f"{header}.{payload}."


@pytest.fixture()
def mock_create_secret() -> Generator[mock.MagicMock]:
    with mock.patch("workspace_api.views.k8s_client.CoreV1Api.create_namespaced_secret") as mocker:
        yield mocker


@pytest.fixture()
def mock_list_ingress() -> Generator[mock.MagicMock]:
    with mock.patch(
        "workspace_api.views.k8s_client.NetworkingV1Api.list_namespaced_ingress",
        return_value=k8s_client.V1IngressList(
            items=[
                k8s_client.V1Ingress(
                    metadata=k8s_client.V1ObjectMeta(name="myingress"),
                    spec=k8s_client.V1IngressSpec(rules=[k8s_client.V1IngressRule(host="example.com")]),
                )
            ]
        ),
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret() -> k8s_client.V1Secret:
    return k8s_client.V1Secret(
        data={
            "access": "",
            "bucketname": "",
            "secret": base64.b64encode(b"supersecret"),
        }
    )


def test_get_workspace_rejects_invalid_names(client: TestClient) -> None:
    response = client.get("/workspaces/not_a_prefix", headers={"Authorization": f"Bearer {_dev_token()}"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_workspace_rejects_missing_audience(client: TestClient) -> None:
    response = client.get(
        "/workspaces/ws-alice",
        headers={"Authorization": f"Bearer {_dev_token(audience=None)}"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {"detail": "Invalid token audience"}


def test_get_workspace_rejects_wrong_audience(client: TestClient) -> None:
    response = client.get(
        "/workspaces/ws-alice",
        headers={"Authorization": f"Bearer {_dev_token(audience=['account'])}"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {"detail": "Invalid token audience"}


def test_get_workspace_accepts_string_audience(client: TestClient) -> None:
    token = _dev_token(
        {"resource-catalogue": {"roles": ["records_editor"]}},
        audience="workspace-api",
    )

    response = client.get(
        "/workspaces/ws-alice",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_get_workspace_rejects_ungranted_workspace(client: TestClient) -> None:
    token = _dev_token({"resource-catalogue": {"roles": ["records_editor"]}})

    response = client.get("/workspaces/ws-alice", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_get_workspace_ws_api_role_returns_only_bucket_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def enc(raw: str) -> str:
        return base64.b64encode(raw.encode()).decode()

    storage = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None, resourceVersion="1"),
        spec={
            "principal": "ws-alice",
            "buckets": [{"bucketName": "ws-alice-data", "discoverable": True}],
        },
    )
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None),
        spec={
            "users": ["alice"],
            "sessions": [{"name": "default", "state": "started"}],
        },
        status={},
    )
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = datalab
    secret = SimpleNamespace(
        metadata=SimpleNamespace(name="ws-alice-datalab"),
        data={
            "BUCKET": enc("ws-alice-data"),
            "AWS_ACCESS_KEY_ID": enc("alice-access"),
            "AWS_SECRET_ACCESS_KEY": enc("alice-secret"),
            "AWS_ENDPOINT_URL": enc("https://s3.example"),
            "AWS_REGION": enc("example"),
        },
    )

    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: storage)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_available_store_types", lambda _datalab_installed: [])
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    monkeypatch.setattr(views, "fetch_secret", lambda *_args: secret)
    token = _dev_token({"ws-alice": {"roles": ["ws_api"]}})

    response = client.get("/workspaces/ws-alice", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["storage"]["credentials"] == {
        "bucketname": "ws-alice-data",
        "access": "alice-access",
        "secret": "alice-secret",
        "endpoint": "https://s3.example",
        "region": "example",
    }
    assert data["storage"]["buckets"] == []
    assert data["storage"]["bucket_access_requests"] == []
    assert data["datalab"]["memberships"] == []
    assert data["datalab"]["stores"] == []
    assert data["datalab"]["sessions"] == []
    assert data["user"]["permissions"] == ["VIEW_BUCKET_CREDENTIALS"]


def _storage_list(*names: str) -> SimpleNamespace:
    return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name=name)) for name in names])


def _datalab_list(*items: tuple[str, list[dict[str, str]]]) -> SimpleNamespace:
    return SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name=name),
                spec={"sessions": sessions},
                status={},
            )
            for name, sessions in items
        ]
    )


def test_list_workspaces_returns_all_storage_workspaces_for_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = _storage_list("ws-bob", "ws-alice")
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = _datalab_list(
        (
            "ws-alice",
            [
                {"name": "default", "state": "started"},
                {"name": "analysis", "state": "stopped"},
            ],
        ),
        ("ws-bob", [{"name": "default", "state": "started"}]),
    )
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {
            "name": "ws-alice",
            "url": "http://testserver/workspaces/ws-alice",
            "sessions": [
                {
                    "name": "default",
                    "url": "http://testserver/workspaces/ws-alice/sessions/default",
                }
            ],
        },
        {
            "name": "ws-bob",
            "url": "http://testserver/workspaces/ws-bob",
            "sessions": [
                {
                    "name": "default",
                    "url": "http://testserver/workspaces/ws-bob/sessions/default",
                }
            ],
        },
    ]


def test_list_workspaces_returns_html_for_browser(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = _storage_list("ws-alice")
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = _datalab_list(
        (
            "ws-alice",
            [
                {"name": "default", "state": "started"},
                {"name": "analysis", "state": "stopped"},
            ],
        )
    )
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)

    response = client.get(
        "/workspaces",
        headers={"Authorization": f"Bearer {_dev_token()}", "Accept": "text/html"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>Workspaces</h1>" in response.text
    assert "href='http://testserver/workspaces/ws-alice'" in response.text
    assert "<span>ws-alice</span><svg class='open-icon'" in response.text
    assert "href='http://testserver/workspaces/ws-alice/sessions/default'" in response.text
    assert "<span>Datalab (default)</span><svg class='open-icon'" in response.text
    assert "&#128279;" not in response.text
    assert "analysis" not in response.text


def test_list_workspaces_keeps_workspace_when_datalab_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = _storage_list("ws-alice")
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: None)

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {
            "name": "ws-alice",
            "url": "http://testserver/workspaces/ws-alice",
            "sessions": [],
        }
    ]


def test_list_workspaces_ws_api_role_lists_workspace_without_sessions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = _storage_list("ws-alice")
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = _datalab_list(
        ("ws-alice", [{"name": "default", "state": "started"}]),
    )
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    token = _dev_token({"ws-alice": {"roles": ["ws_api"]}})

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {
            "name": "ws-alice",
            "url": "http://testserver/workspaces/ws-alice",
            "sessions": [],
        }
    ]


def test_list_workspaces_filters_actual_workspaces_by_explicit_grants(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = _storage_list("ws-alice", "ws-bob", "ws-eric")
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: None)
    token = _dev_token(
        {
            "ws-bob": {"roles": ["ws_access"]},
            "ws-stale-alice": {"roles": ["ws_admin"]},
            "resource-catalogue": {"roles": ["records_editor"]},
        }
    )

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {
            "name": "ws-bob",
            "url": "http://testserver/workspaces/ws-bob",
            "sessions": [],
        }
    ]
