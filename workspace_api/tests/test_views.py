# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs

import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi.testclient import TestClient
from kubernetes import client as k8s_client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

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


def test_get_workspace_rejects_ungranted_workspace(client: TestClient) -> None:
    token = _dev_token({"resource-catalogue": {"roles": ["records_editor"]}})

    response = client.get("/workspaces/ws-alice", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.FORBIDDEN


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

    monkeypatch.setattr(views, "_get_cr", lambda _api, kind, *_args, **_kwargs: storage if kind == views.KIND_STORAGE else datalab)
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

    monkeypatch.setattr(views, "_get_cr", lambda _api, kind, *_args, **_kwargs: storage if kind == views.KIND_STORAGE else datalab)
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


@pytest.mark.parametrize("phase", ["Running", "Pending"])
def test_list_workspaces_returns_names_from_both_providers(client: TestClient, monkeypatch: pytest.MonkeyPatch, phase: str) -> None:
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
        ("ws-jane", []),
    )
    datalab_api.get.return_value.items[0].status = {
        "sessions": [
            {"name": "default", "state": "started", "phase": phase, "url": "https://default.example.org/workspace"},
            {"name": "notebook", "state": "started", "phase": "Running", "url": "https://notebook.example.org/workspace"},
        ]
    }
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {
            "name": "ws-alice",
            "url": "http://testserver/workspaces/ws-alice",
            "sessions": [
                *([{"name": "default", "url": "https://default.example.org/workspace"}] if phase == "Running" else []),
                {"name": "notebook", "url": "https://notebook.example.org/workspace"},
            ],
        },
        {
            "name": "ws-bob",
            "url": "http://testserver/workspaces/ws-bob",
            "sessions": [],
        },
        {"name": "ws-jane", "url": "http://testserver/workspaces/ws-jane", "sessions": []},
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
    datalab_api.get.return_value.items[0].status = {
        "sessions": [{"name": "default", "state": "started", "phase": "Running", "url": "https://published.example.org/workspace"}]
    }
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)

    response = client.get(
        "/workspaces",
        headers={"Authorization": f"Bearer {_dev_token()}", "Accept": "text/html"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>Workspaces</h1>" in response.text
    assert "href='http://testserver/workspaces/ws-alice?resolve_connections=*&amp;resolve_oauth2=*'" in response.text
    assert "href='https://published.example.org/workspace'" in response.text
    assert "analysis" not in response.text


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
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else datalab_api)
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
    monkeypatch.setattr(views, "_res_optional", lambda _api, kind: storage_api if kind == views.KIND_STORAGE else None)
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


def test_workspace_token_allows_requested_workspace_admin_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: None)
    token = _dev_token({"ws-bob": {"roles": ["ws_admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["detail"] == "Workspace not found"


def test_workspace_token_rejects_admin_of_different_workspace(client: TestClient) -> None:
    token = _dev_token({"ws-alice": {"roles": ["ws_admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.fixture
def workspace_oauth(monkeypatch: pytest.MonkeyPatch, requests_mock) -> SimpleNamespace:
    entry = {
        "name": "ws-bob",
        "type": "client",
        "ready": True,
        "issuerUrl": "https://iam.example.org/realms/workspaces",
        "secretRef": {"name": "published-workspace-client", "namespace": "identity"},
    }
    datalab = SimpleNamespace(status={"oauth2": [entry]})
    monkeypatch.setattr(views, "_get_cr", lambda *_args, **_kwargs: datalab)
    discovery = requests_mock.get(
        "https://iam.example.org/realms/workspaces/.well-known/openid-configuration",
        json={"issuer": entry["issuerUrl"], "token_endpoint": "https://tokens.example.org/workspaces"},
    )
    return SimpleNamespace(entry=entry, datalab=datalab, discovery=discovery)


def test_workspace_token_exchanges_workspace_oauth_client_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    requests_mock,
    workspace_oauth: SimpleNamespace,
) -> None:
    monkeypatch.setattr(views.config, "AUTH_AUDIENCE", "workspace-api")

    oauth_secret = SimpleNamespace(
        data={
            "clientSecret": _encoded_secret_value("bob-secret"),
            "attribute.client_secret": _encoded_secret_value("unused-copy"),
            "clientID": _encoded_secret_value("unused-client-id"),
            "certificate": base64.b64encode(b"\xff").decode(),
        },
    )
    read_secret = mock.Mock(return_value=oauth_secret)
    monkeypatch.setattr(views, "fetch_secret", read_secret)

    issued_token = _dev_token({"ws-bob": {"roles": ["ws_api"]}}, audience="workspace-api")
    token_request = requests_mock.post(
        "https://tokens.example.org/workspaces",
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
    assert workspace_oauth.discovery.called
    read_secret.assert_called_once_with("published-workspace-client", "identity")
    assert token_request.last_request is not None
    basic = token_request.last_request.headers["Authorization"].removeprefix("Basic ")
    assert base64.b64decode(basic).decode() == "ws-bob:bob-secret"
    assert token_request.last_request.text == "grant_type=client_credentials&audience=workspace-api"


def test_workspace_token_rejects_authorization_server_token_without_ws_api_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    requests_mock,
    workspace_oauth: SimpleNamespace,
) -> None:
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
    requests_mock.post("https://tokens.example.org/workspaces", json={"access_token": issued_token, "token_type": "Bearer"})
    broker_token = _dev_token({"workspace-api": {"roles": ["admin"]}})

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {broker_token}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"


@pytest.mark.parametrize("state, expected", [("missing", 404), ("not_ready", 503), ("ambiguous", 502)])
def test_workspace_token_requires_one_ready_published_client(
    client: TestClient, workspace_oauth: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, requests_mock, state: str, expected: int
) -> None:
    if state == "missing":
        workspace_oauth.entry["name"] = "catalog-integration"
    elif state == "not_ready":
        workspace_oauth.entry["ready"] = False
    else:
        workspace_oauth.datalab.status["oauth2"].append(dict(workspace_oauth.entry))
    read_secret = mock.Mock()
    monkeypatch.setattr(views, "fetch_secret", read_secret)

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == expected
    read_secret.assert_not_called()
    assert not requests_mock.called


@pytest.mark.parametrize(
    "metadata",
    [
        {"issuer": "https://other.example.org", "token_endpoint": "https://tokens.example.org/workspaces"},
        {"issuer": "https://iam.example.org/realms/workspaces"},
        {"issuer": "https://iam.example.org/realms/workspaces", "token_endpoint": "http://tokens.example.org/workspaces"},
    ],
)
def test_workspace_token_rejects_invalid_issuer_metadata_before_secret_access(
    client: TestClient, workspace_oauth: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, requests_mock, metadata
) -> None:
    requests_mock.get("https://iam.example.org/realms/workspaces/.well-known/openid-configuration", json=metadata)
    read_secret = mock.Mock()
    monkeypatch.setattr(views, "fetch_secret", read_secret)

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "oauth_discovery_invalid"
    read_secret.assert_not_called()


def test_workspace_token_does_not_follow_discovery_redirects(
    client: TestClient, workspace_oauth: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, requests_mock
) -> None:
    requests_mock.get(
        "https://iam.example.org/realms/workspaces/.well-known/openid-configuration",
        status_code=302,
        headers={"Location": "https://other.example.org/discovery"},
    )
    read_secret = mock.Mock()
    monkeypatch.setattr(views, "fetch_secret", read_secret)

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert len(requests_mock.request_history) == 1
    read_secret.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        {"attribute.client_secret": _encoded_secret_value("test-value"), "client_secret": _encoded_secret_value("other-value")},
        {"oauth-client.json": _encoded_secret_value(json.dumps({"clientSecret": "test-value"}))},
        {"clientSecret": "invalid base64"},
        {"clientSecret": _encoded_secret_value(" ")},
    ],
)
def test_workspace_token_requires_client_secret_field(
    client: TestClient, workspace_oauth: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, requests_mock, data: dict[str, str]
) -> None:
    monkeypatch.setattr(
        views,
        "fetch_secret",
        lambda *_args: SimpleNamespace(data=data),
    )

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "oauth_client_secret_invalid"
    assert all(request.method == "GET" for request in requests_mock.request_history)


def test_workspace_token_requires_a_reported_token_type(
    client: TestClient, workspace_oauth: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, requests_mock
) -> None:
    monkeypatch.setattr(views, "fetch_secret", lambda *_args: SimpleNamespace(data={"clientSecret": _encoded_secret_value("test-value")}))
    requests_mock.post(
        "https://tokens.example.org/workspaces",
        json={"access_token": _dev_token({"ws-bob": {"roles": ["ws_api"]}})},
    )

    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {_dev_token()}"})

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"


@pytest.fixture(scope="module")
def token_signing_key():
    return JsonWebKey.generate_key("RSA", 2048, options={"kid": "workspace"}, is_private=True)


def _signed_exchange_token(exchange: SimpleNamespace, claims: dict | None = None) -> str:
    return JsonWebToken(["RS256"]).encode({"alg": "RS256", "kid": "workspace"}, claims or exchange.claims, exchange.key).decode()


@pytest.fixture
def workspace_exchange(
    workspace_oauth: SimpleNamespace, token_signing_key, monkeypatch: pytest.MonkeyPatch, requests_mock
) -> SimpleNamespace:
    scope = "ws-bob:vclusters_vc0_namespace-demo"
    role = "vcluster_vc0_namespace-demo"
    workspace_oauth.datalab.spec = {
        "vclusters": {
            "vc0": {
                "groups": [
                    {"name": "namespace-demo", "namespace": "demo", "role": "edit"},
                    {"name": "cluster-admin", "namespace": "*", "role": "cluster-admin"},
                ]
            },
            "vc1": {"groups": [{"name": "analysis", "namespace": "analysis", "role": "view"}]},
        }
    }
    workspace_oauth.datalab.status["connections"] = [
        {"type": "vcluster", "instance": "vc0", "group": "namespace-demo", "targetNamespace": "demo", "role": "edit", "ready": True},
        {"type": "vcluster", "instance": "vc1", "group": "analysis", "targetNamespace": "analysis", "role": "view", "ready": True},
    ]
    issuer = workspace_oauth.entry["issuerUrl"]
    requests_mock.get(
        f"{issuer}/.well-known/openid-configuration",
        json={"issuer": issuer, "token_endpoint": "https://tokens.example.org/workspaces", "jwks_uri": f"{issuer}/certs"},
    )
    requests_mock.get(f"{issuer}/certs", json={"keys": [token_signing_key.as_dict()]})
    read_secret = mock.Mock(return_value=SimpleNamespace(data={"clientSecret": _encoded_secret_value("bob-secret")}))
    monkeypatch.setattr(views, "fetch_secret", read_secret)
    claims = {
        "iss": issuer,
        "sub": "workspace-user",
        "aud": ["workspace-api", "ws-bob"],
        "exp": int(datetime.now(UTC).timestamp()) + 300,
        "scope": f"profile email {scope}",
        "resource_access": {"ws-bob": {"roles": ["ws_api", role]}},
    }
    caller = {**claims, "resource_access": {"ws-bob": {"roles": ["ws_admin", "ws_api", role, "vcluster_vc1_analysis"]}}}
    exchange = SimpleNamespace(key=token_signing_key, claims=claims, caller=caller, scope=scope, role=role, read_secret=read_secret)
    exchange.subject_token = _signed_exchange_token(exchange, caller)
    exchange.access_token = _signed_exchange_token(exchange)
    exchange.response = {
        "access_token": exchange.access_token,
        "token_type": "Bearer",
        "expires_in": 300,
        "scope": claims["scope"],
        "refresh_token": "must-not-be-forwarded",
    }
    exchange.endpoint = requests_mock.post("https://tokens.example.org/workspaces", json=exchange.response)
    return exchange


def test_workspace_token_exchanges_original_user_token_for_selected_profiles(
    client: TestClient, workspace_exchange: SimpleNamespace
) -> None:
    exchange = workspace_exchange
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {name: exchange.response[name] for name in ("access_token", "token_type", "expires_in", "scope")}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    exchange.read_secret.assert_called_once_with("published-workspace-client", "identity")
    sent = exchange.endpoint.last_request
    assert sent is not None
    assert sent.qs == {}
    assert base64.b64decode(sent.headers["Authorization"].removeprefix("Basic ")).decode() == "ws-bob:bob-secret"
    assert parse_qs(sent.text) == {
        "grant_type": ["urn:ietf:params:oauth:grant-type:token-exchange"],
        "subject_token": [exchange.subject_token],
        "subject_token_type": ["urn:ietf:params:oauth:token-type:access_token"],
        "requested_token_type": ["urn:ietf:params:oauth:token-type:access_token"],
        "scope": [exchange.scope],
        "audience": ["workspace-api", "ws-bob"],
    }


@pytest.mark.parametrize(
    "scope",
    [
        "",
        "  ",
        "ws-bob:interactive",
        "ws-bob:vclusters_vc0_cluster-admin",
        "ws-other:vclusters_vc0_namespace-demo",
        "vcluster_vc0_namespace-demo",
    ],
)
def test_workspace_exchange_rejects_unconfigured_scopes_before_credentials(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, scope: str
) -> None:
    exchange = workspace_exchange
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["error"] == "invalid_scope"
    exchange.read_secret.assert_not_called()
    assert not requests_mock.called


def test_workspace_exchange_rejects_removed_profile(
    client: TestClient, workspace_exchange: SimpleNamespace, workspace_oauth: SimpleNamespace, requests_mock
) -> None:
    workspace_oauth.datalab.spec["vclusters"]["vc0"]["groups"] = []
    exchange = workspace_exchange
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    exchange.read_secret.assert_not_called()
    assert not requests_mock.called


@pytest.mark.parametrize(
    "claims",
    [
        {"resource_access": {"workspace-api": {"roles": ["admin"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_admin", "vcluster_vc0_namespace-demo"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_admin", "ws_api"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_access", "ws_api", "vcluster_vc0_namespace-demo"]}}},
        {"iss": "https://other.example.org/realms/workspaces"},
        {"sub": ""},
        {"aud": ["workspace-api"]},
    ],
)
def test_workspace_exchange_requires_issuance_permission_and_caller_grants(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, claims: dict
) -> None:
    exchange = workspace_exchange
    subject_token = _signed_exchange_token(exchange, {**exchange.caller, **claims})
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {subject_token}"}
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    exchange.read_secret.assert_not_called()
    assert not requests_mock.called


def test_workspace_exchange_accepts_own_client_subject_and_multiple_profiles(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock
) -> None:
    exchange = workspace_exchange
    scopes = f"{exchange.scope} ws-bob:vclusters_vc1_analysis"
    claims = {
        **exchange.claims,
        "scope": scopes,
        "resource_access": {"ws-bob": {"roles": ["ws_api", exchange.role, "vcluster_vc1_analysis"]}},
    }
    issued = _signed_exchange_token(exchange, claims)
    requests_mock.post("https://tokens.example.org/workspaces", json={**exchange.response, "access_token": issued, "scope": scopes})
    caller = _signed_exchange_token(exchange, {**exchange.caller, "aud": ["workspace-api"], "azp": "ws-bob"})

    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": f"{scopes} {exchange.scope}"}, headers={"Authorization": f"Bearer {caller}"}
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["access_token"] == issued


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://other.example.org/realms/workspaces"},
        {"sub": "another-user"},
        {"sub": "service-account-ws-bob"},
        {"exp": 1},
        {"exp": None},
        {"nbf": 4102444800},
        {"aud": ["workspace-api"]},
        {"aud": ["workspace-api", "ws-bob", "ws-other"]},
        {"scope": "ws-bob:interactive"},
        {"scope": "ws-bob:vclusters_vc0_namespace-demo offline_access"},
        {"resource_access": {"ws-bob": {"roles": ["ws_api"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_api", "vcluster_vc0_namespace-demo", "ws_admin"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_api", "vcluster_vc0_namespace-demo", "vcluster_vc0_cluster-admin"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_api", "vcluster_vc0_namespace-demo", "vcluster_vc1_analysis"]}}},
        {"resource_access": {"ws-bob": {"roles": ["ws_api", "vcluster_vc0_namespace-demo"]}, "workspace-api": {"roles": ["admin"]}}},
        {"realm_access": {"roles": ["realm-admin"]}},
        {"authorization": {"permissions": [{"rsname": "another-service"}]}},
    ],
)
def test_workspace_exchange_rejects_invalid_or_excessive_token_claims(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, claims: dict
) -> None:
    exchange = workspace_exchange
    issued = _signed_exchange_token(exchange, {**exchange.claims, **claims})
    requests_mock.post("https://tokens.example.org/workspaces", json={**exchange.response, "access_token": issued})

    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"
    assert issued not in response.text


@pytest.mark.parametrize("signed", [False, True])
def test_workspace_exchange_requires_issuer_signature(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, signed: bool
) -> None:
    exchange = workspace_exchange
    if signed:
        other_key = JsonWebKey.generate_key("RSA", 2048, options={"kid": "workspace"}, is_private=True)
        issued = JsonWebToken(["RS256"]).encode({"alg": "RS256", "kid": "workspace"}, exchange.claims, other_key).decode()
    else:
        issued = _dev_token({"ws-bob": {"roles": ["ws_api", exchange.role]}}, audience=["workspace-api", "ws-bob"])
    requests_mock.post("https://tokens.example.org/workspaces", json={**exchange.response, "access_token": issued})

    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"


def test_workspace_exchange_requires_requested_scope_in_response(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock
) -> None:
    exchange = workspace_exchange
    requests_mock.post("https://tokens.example.org/workspaces", json={**exchange.response, "scope": "profile email"})
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


@pytest.mark.parametrize("uri", [None, "http://iam.example.org/certs"])
def test_workspace_exchange_requires_https_signing_keys_before_credentials(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, uri: str | None
) -> None:
    exchange = workspace_exchange
    issuer = exchange.claims["iss"]
    requests_mock.get(
        f"{issuer}/.well-known/openid-configuration",
        json={"issuer": issuer, "token_endpoint": "https://tokens.example.org/workspaces", "jwks_uri": uri},
    )
    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    exchange.read_secret.assert_not_called()
    assert not exchange.endpoint.called


def test_workspace_broker_rejects_service_account_token_with_additional_roles(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock
) -> None:
    exchange = workspace_exchange
    response = client.get("/workspaces/ws-bob/token", headers={"Authorization": f"Bearer {exchange.subject_token}"})
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"]["error"] == "token_validation_failed"


@pytest.mark.parametrize("failure", ["redirect", "unavailable", "invalid_json", "empty_keys"])
def test_workspace_exchange_stops_when_signing_keys_are_unavailable(
    client: TestClient, workspace_exchange: SimpleNamespace, requests_mock, failure: str
) -> None:
    exchange = workspace_exchange
    responses = {
        "redirect": {"status_code": 302, "headers": {"Location": "https://other.example.org/certs"}},
        "unavailable": {"status_code": 503},
        "invalid_json": {"text": "not JSON"},
        "empty_keys": {"json": {"keys": []}},
    }
    requests_mock.get(f"{exchange.claims['iss']}/certs", **responses[failure])

    response = client.get(
        "/workspaces/ws-bob/token", params={"scope": exchange.scope}, headers={"Authorization": f"Bearer {exchange.subject_token}"}
    )

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    exchange.read_secret.assert_not_called()
    assert not exchange.endpoint.called
    assert len(requests_mock.request_history) == 2


@pytest.mark.parametrize("change", ["missing", "preparing", "namespace", "role"])
def test_exchange_requires_current_published_ready_profile(
    client: TestClient, workspace_exchange: SimpleNamespace, workspace_oauth: SimpleNamespace, change: str
) -> None:
    entries = workspace_oauth.datalab.status["connections"]
    if change == "missing":
        entries.clear()
    elif change == "preparing":
        entries[0]["ready"] = False
    elif change == "namespace":
        entries[0]["targetNamespace"] = "old-demo"
    else:
        entries[0]["role"] = "admin"
    response = client.get(
        "/workspaces/ws-bob/token",
        params={"scope": workspace_exchange.scope},
        headers={"Authorization": f"Bearer {workspace_exchange.subject_token}"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "vcluster_profile_not_ready"
    workspace_exchange.read_secret.assert_not_called()
    assert not workspace_exchange.endpoint.called
