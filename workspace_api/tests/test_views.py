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
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from workspace_api import views
from workspace_api.models import ROLE_TO_PERMISSIONS


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
    monkeypatch.setattr(
        views.k8s_client,
        "CoreV1Api",
        mock.MagicMock(side_effect=AssertionError("ws_api must not read workspace resource usage")),
    )
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
    assert "resource_usage" not in data
    assert data["user"]["permissions"] == ["VIEW_BUCKET_CREDENTIALS"]


def test_get_workspace_returns_storage_quota_pvcs_sum_and_remaining(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None, resourceVersion="1"),
        spec={"principal": "ws-alice", "buckets": []},
    )
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None),
        spec={"users": ["alice"], "sessions": []},
        status={},
    )
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = datalab
    core_api = mock.MagicMock()
    core_api.list_namespaced_resource_quota.return_value = k8s_client.V1ResourceQuotaList(
        items=[
            k8s_client.V1ResourceQuota(
                metadata=k8s_client.V1ObjectMeta(name="workspace-storage"),
                status=k8s_client.V1ResourceQuotaStatus(
                    hard={"requests.storage": "10Gi"},
                    used={"requests.storage": "1536Mi"},
                ),
            )
        ]
    )
    core_api.list_namespaced_persistent_volume_claim.return_value = k8s_client.V1PersistentVolumeClaimList(
        items=[
            k8s_client.V1PersistentVolumeClaim(
                metadata=k8s_client.V1ObjectMeta(name="workspace-data"),
                spec=k8s_client.V1PersistentVolumeClaimSpec(resources=k8s_client.V1VolumeResourceRequirements(requests={"storage": "1Gi"})),
            ),
            k8s_client.V1PersistentVolumeClaim(
                metadata=k8s_client.V1ObjectMeta(name="cache"),
                spec=k8s_client.V1PersistentVolumeClaimSpec(
                    resources=k8s_client.V1VolumeResourceRequirements(requests={"storage": "512Mi"})
                ),
            ),
        ]
    )

    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: storage)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_available_store_types", lambda _datalab_installed: [])
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    monkeypatch.setattr(views, "fetch_secret", lambda *_args: None)
    monkeypatch.setattr(views.k8s_client, "CoreV1Api", lambda: core_api)

    response = client.get("/workspaces/ws-alice", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["resource_usage"] == {
        "storage": {
            "quota": "10Gi",
            "requested": "1536Mi",
            "remaining": "8704Mi",
            "persistent_volume_claims": [
                {"name": "cache", "size": "512Mi"},
                {"name": "workspace-data", "size": "1Gi"},
            ],
        }
    }
    core_api.list_namespaced_resource_quota.assert_called_once_with(namespace="ws-alice")
    core_api.list_namespaced_persistent_volume_claim.assert_called_once_with(namespace="ws-alice")


def test_get_workspace_omits_resource_usage_when_kubernetes_access_is_forbidden(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None, resourceVersion="1"),
        spec={"principal": "ws-alice", "buckets": []},
    )
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None),
        spec={"users": ["alice"], "sessions": []},
        status={},
    )
    datalab_api = mock.MagicMock()
    datalab_api.get.return_value = datalab
    core_api = mock.MagicMock()
    core_api.list_namespaced_resource_quota.side_effect = ApiException(status=HTTPStatus.FORBIDDEN)

    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: storage)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: datalab_api)
    monkeypatch.setattr(views, "_available_store_types", lambda _datalab_installed: [])
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    monkeypatch.setattr(views, "fetch_secret", lambda *_args: None)
    monkeypatch.setattr(views.k8s_client, "CoreV1Api", lambda: core_api)

    response = client.get("/workspaces/ws-alice", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.OK
    assert "resource_usage" not in response.json()


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


def _encoded_secret_value(raw: str) -> str:
    return base64.b64encode(raw.encode()).decode()


def test_only_ws_admin_role_grants_issue_tokens_permission() -> None:
    assert "ISSUE_TOKENS" in {permission.value for permission in ROLE_TO_PERMISSIONS["ws_admin"]}
    assert "ISSUE_TOKENS" not in {permission.value for permission in ROLE_TO_PERMISSIONS["ws_access"]}
    assert "ISSUE_TOKENS" not in {permission.value for permission in ROLE_TO_PERMISSIONS["ws_api"]}


def test_workspace_token_allows_requested_workspace_admin_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views.config, "TOKEN_BROKER_TOKEN_ENDPOINT", "")
    token = _dev_token({"ws-bob": {"roles": ["ws_admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"]["error"] == "token_broker_not_configured"


def test_workspace_token_rejects_admin_of_different_workspace(client: TestClient) -> None:
    token = _dev_token({"ws-alice": {"roles": ["ws_admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_workspace_token_exchanges_workspace_oauth_client_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    requests_mock,
) -> None:
    monkeypatch.setattr(views.config, "TOKEN_BROKER_TOKEN_ENDPOINT", "http://idp.example/realms/main/protocol/openid-connect/token")
    monkeypatch.setattr(views.config, "AUTH_AUDIENCE", "workspace-api")

    oauth_secret = SimpleNamespace(
        metadata=SimpleNamespace(name="ws-bob-oauth-client"),
        data={
            "clientID": _encoded_secret_value("ws-bob"),
            "clientSecret": _encoded_secret_value("bob-secret"),
        },
    )
    monkeypatch.setattr(views, "fetch_secret", lambda name, _namespace: oauth_secret if name == "ws-bob-oauth-client" else None)

    issued_token = _dev_token({"ws-bob": {"roles": ["ws_api"]}}, audience="workspace-api")
    token_request = requests_mock.post(
        "http://idp.example/realms/main/protocol/openid-connect/token",
        json={
            "access_token": issued_token,
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_token": "should-not-be-forwarded",
        },
    )
    broker_token = _dev_token({"workspace-api": {"roles": ["admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {broker_token}"})

    assert response.status_code == HTTPStatus.OK
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json() == {
        "access_token": issued_token,
        "token_type": "Bearer",
        "expires_in": 300,
        "scope": None,
    }
    assert token_request.called
    assert token_request.last_request is not None
    basic = token_request.last_request.headers["Authorization"].removeprefix("Basic ")
    assert base64.b64decode(basic).decode() == "ws-bob:bob-secret"
    assert token_request.last_request.text == "grant_type=client_credentials&audience=workspace-api"


def test_workspace_token_accepts_json_encoded_oauth_client_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    requests_mock,
) -> None:
    monkeypatch.setattr(views.config, "TOKEN_BROKER_TOKEN_ENDPOINT", "https://idp.example/token")
    monkeypatch.setattr(views.config, "AUTH_AUDIENCE", "workspace-api")

    oauth_secret = SimpleNamespace(
        metadata=SimpleNamespace(name="ws-bob-oauth-client"),
        data={
            "oauth-client.json": _encoded_secret_value(
                json.dumps(
                    {
                        "clientID": "ws-bob",
                        "clientSecret": "bob-secret",
                    }
                )
            )
        },
    )
    monkeypatch.setattr(views, "fetch_secret", lambda name, _namespace: oauth_secret if name == "ws-bob-oauth-client" else None)

    issued_token = _dev_token({"ws-bob": {"roles": ["ws_api"]}}, audience="workspace-api")
    requests_mock.post("https://idp.example/token", json={"access_token": issued_token, "token_type": "Bearer"})
    broker_token = _dev_token({"workspace-api": {"roles": ["admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {broker_token}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["access_token"] == issued_token


def test_workspace_token_rejects_authorization_server_token_without_ws_api_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    requests_mock,
) -> None:
    monkeypatch.setattr(views.config, "TOKEN_BROKER_TOKEN_ENDPOINT", "https://idp.example/token")
    monkeypatch.setattr(views.config, "AUTH_AUDIENCE", "workspace-api")

    oauth_secret = SimpleNamespace(
        metadata=SimpleNamespace(name="ws-bob-oauth-client"),
        data={
            "clientID": _encoded_secret_value("ws-bob"),
            "clientSecret": _encoded_secret_value("bob-secret"),
        },
    )
    monkeypatch.setattr(views, "fetch_secret", lambda *_args: oauth_secret)
    issued_token = _dev_token({"ws-bob": {"roles": ["ws_access"]}}, audience="workspace-api")
    requests_mock.post("https://idp.example/token", json={"access_token": issued_token, "token_type": "Bearer"})
    broker_token = _dev_token({"workspace-api": {"roles": ["admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {broker_token}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"


def test_workspace_token_requires_configured_token_endpoint(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views.config, "TOKEN_BROKER_TOKEN_ENDPOINT", "")
    broker_token = _dev_token({"workspace-api": {"roles": ["admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {broker_token}"})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"]["error"] == "token_broker_not_configured"
