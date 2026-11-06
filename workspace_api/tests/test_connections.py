# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from workspace_api import config, views
from workspace_api.models import StoreType
from workspace_api.tests.test_views import _dev_token
from workspace_api.views import _extract_relevant_bucket_access_requests

S3_VALUE = "test-s3-key"


@pytest.fixture
def connection_workspace(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    def secret(values: dict[str, str]) -> SimpleNamespace:
        return SimpleNamespace(data={key: base64.b64encode(value.encode()).decode() for key, value in values.items()})

    connections = [
        {
            "name": name,
            "type": kind,
            "ready": True,
            "endpoint": "https://services.example.org",
            "secretRef": {"name": f"ws-alice-{name}", "namespace": "workspace"},
        }
        for name, kind in (
            ("pg0", "postgres"),
            ("mongo-docs", "mongo"),
            ("redis-cache", "redis"),
            ("catalog", "custom"),
            ("vcluster-administrators", "vcluster"),
            ("vcluster-editors", "vcluster"),
        )
    ]
    connections[4].update(group="administrators", targetNamespace="*", role="cluster-admin")
    connections[5].update(group="editors", targetNamespace="analysis", role="edit")
    connections.append(
        {
            "name": "primary",
            "type": "s3",
            "ready": True,
            "endpoint": "https://s3.example.org",
            "region": "test-region",
            "secretRef": {"name": "ws-alice-s3", "namespace": "workspace"},
        }
    )
    oauth2_names = ("ws-alice", "catalog-integration")
    oauth2 = [
        {
            "name": name,
            "type": "client",
            "issuerUrl": "https://iam.example.org/realms/workspaces",
            "ready": True,
            "secretRef": {"name": f"{name}-oauth-client", "namespace": "workspace"},
        }
        for name in oauth2_names
    ]
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None),
        spec={
            "users": ["alice"],
            "databases": {"pg0": {"names": ["analytics", "reports"]}},
            "documentStores": {"docs": {}},
            "cacheStores": {"cache": {}},
            "sessions": [],
        },
        status={"connections": connections, "oauth2": oauth2},
    )
    storage = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None, resourceVersion="1"),
        spec={"principal": "ws-alice", "buckets": [{"bucketName": "ws-alice"}]},
    )
    secrets = {f"ws-alice-{item['name']}": secret({"password": "test-value"}) for item in connections}
    secrets["ws-alice"] = secret(
        {
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": S3_VALUE,
            "AWS_ENDPOINT_URL": "https://old-s3.example.org",
            "AWS_REGION": "old-region",
        }
    )
    secrets["ws-alice-s3"] = secrets["ws-alice"]
    secrets.update({f"{name}-oauth-client": secret({"clientID": name, "clientSecret": "test-value"}) for name in oauth2_names})
    read_secret = mock.Mock(side_effect=lambda name, _namespace: secrets.get(name))
    monkeypatch.setattr(views, "fetch_secret", read_secret)
    monkeypatch.setattr(views, "current_namespace", lambda: "workspace")
    storage_read = mock.Mock(return_value=storage)
    monkeypatch.setattr(
        views,
        "_get_cr",
        mock.Mock(side_effect=lambda _api, kind, *_args, **_kwargs: storage_read() if kind == views.KIND_STORAGE else datalab),
    )
    monkeypatch.setattr(views, "_res_optional", lambda *_args: SimpleNamespace(get=lambda **_kwargs: datalab))
    monkeypatch.setattr(views, "_available_store_types", lambda *_args: list(StoreType))
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", lambda *_args: [])
    return SimpleNamespace(
        datalab=datalab, connections=connections, oauth2=oauth2, read_secret=read_secret, secrets=secrets, storage_read=storage_read
    )


def headers(role: str) -> dict[str, str]:
    access = {"workspace-api": {"roles": ["admin"]}} if role == "admin" else {"ws-alice": {"roles": [role]}}
    return {"Authorization": f"Bearer {_dev_token(access)}", "Accept": "application/json"}


def test_metadata_does_not_read_connection_secrets(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.connections[4]["credentials"] = {"password": "status-only-value"}
    connection_workspace.oauth2[0]["credentials"] = {"clientSecret": "status-only-value"}
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=headers("ws_access"))

    assert response.status_code == 200
    data = response.json()
    assert "credentials" not in data["storage"]
    entries = data["datalab"]["connections"]
    assert len(entries) == 7
    assert entries[4]["role"] == "cluster-admin"
    assert entries[5]["target_namespace"] == "analysis"
    assert all("credentials" not in entry for entry in entries)
    assert all(field not in data["datalab"] for field in ("vcluster", "registry"))
    assert [entry["name"] for entry in data["datalab"]["oauth2"]] == ["ws-alice", "catalog-integration"]
    assert all("credentials" not in entry for entry in data["datalab"]["oauth2"])
    assert "test-value" not in response.text and "status-only-value" not in response.text
    assert "store_credentials" not in data["datalab"]
    assert "container_registry_credentials" not in data["datalab"]
    assert response.headers["cache-control"] == "no-store"
    connection_workspace.read_secret.assert_not_called()


@pytest.mark.parametrize("role, selector", [("ws_access", "*"), ("ws_admin", "*:*"), ("admin", "*:*"), ("ws_api", "*")])
def test_workspace_roles_resolve_connections_without_oauth2(
    client: TestClient, connection_workspace: SimpleNamespace, role: str, selector: str
) -> None:
    response = client.get("/workspaces/ws-alice", params={"resolve_connections": selector}, headers=headers(role))

    assert response.status_code == 200
    data = response.json()
    entries = data["datalab"]["connections"]
    assert len(entries) == 7
    assert all(entry["credentials"] == {"password": "test-value"} for entry in entries if entry["type"] != "s3")
    assert data["storage"]["credentials"]["secret"] == S3_VALUE
    assert all("credentials" not in entry for entry in data["datalab"]["oauth2"])
    assert response.headers["cache-control"] == "no-store"
    assert connection_workspace.read_secret.call_count == 7


@pytest.mark.parametrize("selector", ["*", "client:*", "client:ws-alice"])
def test_automation_cannot_resolve_oauth2_or_trigger_secret_reads(
    client: TestClient, connection_workspace: SimpleNamespace, selector: str
) -> None:
    response = client.get("/workspaces/ws-alice", params={"resolve_oauth2": selector}, headers=headers("ws_api"))

    assert response.status_code == 403
    connection_workspace.read_secret.assert_not_called()
    connection_workspace.storage_read.assert_not_called()


@pytest.mark.parametrize("role", ["ws_access", "ws_admin", "admin"])
def test_human_roles_can_resolve_oauth2(client: TestClient, connection_workspace: SimpleNamespace, role: str) -> None:
    response = client.get("/workspaces/ws-alice?resolve_connections=none&resolve_oauth2=*", headers=headers(role))

    assert response.status_code == 200
    entries = response.json()["datalab"]["oauth2"]
    assert all(entry["credentials"] == {"clientID": entry["name"], "clientSecret": "test-value"} for entry in entries)
    assert response.headers["cache-control"] == "no-store"
    assert connection_workspace.read_secret.call_count == 2


@pytest.mark.parametrize(
    "selectors, expected",
    [
        (["client:ws-alice"], {"ws-alice-oauth-client"}),
        (["client:*"], {"ws-alice-oauth-client", "catalog-integration-oauth-client"}),
        (["client:ws-alice", "*:catalog-integration", "*:*"], {"ws-alice-oauth-client", "catalog-integration-oauth-client"}),
        (["ws-alice", "none", "client:missing", "other:*"], set()),
    ],
)
def test_oauth2_selectors_read_only_selected_secrets(
    client: TestClient, connection_workspace: SimpleNamespace, selectors, expected
) -> None:
    response = client.get(
        "/workspaces/ws-alice",
        params=[("resolve_connections", "none"), *(("resolve_oauth2", selector) for selector in selectors)],
        headers=headers("ws_access"),
    )

    assert response.status_code == 200
    assert {call.args[0] for call in connection_workspace.read_secret.call_args_list} == expected
    assert connection_workspace.read_secret.call_count == len(expected)


@pytest.mark.parametrize("failure", ["not_ready", "secret_not_found", "invalid_secret"])
def test_unavailable_oauth2_never_returns_credentials(client: TestClient, connection_workspace: SimpleNamespace, failure: str) -> None:
    entry = connection_workspace.oauth2[0]
    secret_name = entry["secretRef"]["name"]
    if failure == "not_ready":
        entry["ready"] = False
    elif failure == "secret_not_found":
        del connection_workspace.secrets[secret_name]
    else:
        connection_workspace.secrets[secret_name].data = {"clientSecret": "!invalid!"}

    response = client.get("/workspaces/ws-alice?resolve_connections=none&resolve_oauth2=client:ws-alice", headers=headers("ws_access"))

    assert response.status_code == 200
    result = response.json()["datalab"]["oauth2"][0]
    assert "credentials" not in result
    assert result["issuer_url"] == entry["issuerUrl"]
    assert result["resolution_error"] == failure
    if failure == "not_ready":
        connection_workspace.read_secret.assert_not_called()


def test_oauth2_permission_is_scoped_to_the_requested_workspace(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    token = _dev_token({"ws-alice": {"roles": ["ws_api"]}, "ws-other": {"roles": ["ws_admin"]}})
    response = client.get("/workspaces/ws-alice?resolve_oauth2=*", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    connection_workspace.read_secret.assert_not_called()


@pytest.mark.parametrize("role", ["ws_api", "ws_access"])
def test_connection_alias_cannot_resolve_an_oauth2_secret(client: TestClient, connection_workspace: SimpleNamespace, role: str) -> None:
    connection_workspace.connections[0]["secretRef"] = connection_workspace.oauth2[0]["secretRef"]
    response = client.get("/workspaces/ws-alice?resolve_connections=postgres:pg0", headers=headers(role))

    assert response.status_code == 200
    entry = response.json()["datalab"]["connections"][0]
    assert entry["resolution_error"] == "oauth2_reference"
    assert "credentials" not in entry
    connection_workspace.read_secret.assert_not_called()


@pytest.mark.parametrize("failure", ["not_ready", "secret_not_found", "invalid_secret"])
def test_unavailable_connections_keep_metadata_without_credentials(
    client: TestClient, connection_workspace: SimpleNamespace, failure: str
) -> None:
    entry = connection_workspace.connections[4]
    secret_name = entry["secretRef"]["name"]
    if failure == "not_ready":
        entry["ready"] = False
    elif failure == "secret_not_found":
        del connection_workspace.secrets[secret_name]
    else:
        connection_workspace.secrets[secret_name].data = {"password": "!invalid!"}

    response = client.get("/workspaces/ws-alice?resolve_connections=*:*", headers=headers("ws_access"))

    assert response.status_code == 200
    connection = response.json()["datalab"]["connections"][4]
    assert connection["resolution_error"] == failure
    assert "credentials" not in connection
    assert connection["name"] == "vcluster-administrators"
    if failure == "not_ready":
        assert all(call.args[0] != secret_name for call in connection_workspace.read_secret.call_args_list)


@pytest.mark.parametrize("resolve", [False, True])
def test_html_uses_explicit_connection_resolution(
    client: TestClient, connection_workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, resolve: bool
) -> None:
    connection_workspace.datalab.status["sessions"] = [
        {"name": "notebook", "state": "started", "phase": "Running", "url": "https://notebook.example.org/workspace"},
        {"name": "pending", "state": "started", "phase": "Pending"},
    ]
    monkeypatch.setattr(config, "UI_MODE", "ui")
    monkeypatch.setattr(views, "templates", Jinja2Templates(directory=Path("workspace_ui/luigi-shell")))
    request_headers = {**headers("ws_access"), "Accept": "text/html"}
    query = "?resolve_connections=*&resolve_oauth2=*" if resolve else "?resolve_connections=none"
    response = client.get(f"/workspaces/ws-alice{query}", headers=request_headers)

    assert response.status_code == 200
    match = re.search(r"const workspaceData = '([^']+)'", response.text)
    assert match is not None
    data = json.loads(base64.b64decode(match[1]))
    endpoint_match = re.search(r"const endpointsData = '([^']+)'", response.text)
    assert endpoint_match is not None
    assert json.loads(base64.b64decode(endpoint_match[1])) == [
        {"id": "Datalab (notebook)", "url": "https://notebook.example.org/workspace"}
    ]
    assert ("credentials" in data["datalab"]["connections"][4]) is resolve
    assert ("credentials" in data["datalab"]["oauth2"][0]) is resolve
    assert response.headers["cache-control"] == "no-store"
    assert connection_workspace.read_secret.call_count == (9 if resolve else 0)


def test_missing_status_never_reads_legacy_secrets(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.connections.clear()
    connection_workspace.oauth2.clear()
    response = client.get("/workspaces/ws-alice?resolve_connections=*&resolve_oauth2=*", headers=headers("ws_access"))

    assert response.status_code == 200
    assert "credentials" not in response.json()["storage"]
    assert response.json()["datalab"]["connections"] == []
    assert response.json()["datalab"]["oauth2"] == []
    connection_workspace.read_secret.assert_not_called()


def test_storage_credentials_use_published_endpoint_and_region(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.connections[-1]["endpoint"] = "https://published-s3.example.org/storage"
    connection_workspace.connections[-1]["region"] = "published-region"

    response = client.get("/workspaces/ws-alice", headers=headers("ws_api"))

    assert response.status_code == 200
    assert response.json()["storage"]["credentials"]["endpoint"] == "https://published-s3.example.org/storage"
    assert response.json()["storage"]["credentials"]["region"] == "published-region"
    assert response.json()["datalab"]["connections"][-1]["region"] == "published-region"
    connection_workspace.read_secret.assert_called_once_with("ws-alice-s3", "workspace")


@pytest.mark.parametrize("field", ["endpoint", "region"])
def test_storage_credentials_do_not_replace_missing_status_data(
    client: TestClient, connection_workspace: SimpleNamespace, field: str
) -> None:
    del connection_workspace.connections[-1][field]

    response = client.get("/workspaces/ws-alice", headers=headers("ws_api"))

    assert response.status_code == 200
    assert "credentials" not in response.json()["storage"]
    assert response.json()["datalab"]["connections"][-1]["credentials"]["AWS_SECRET_ACCESS_KEY"] == S3_VALUE


def test_storage_credentials_require_standard_aws_keys(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.secrets["ws-alice-s3"].data = {
        "username": base64.b64encode(b"test-access-key").decode(),
        "password": base64.b64encode(S3_VALUE.encode()).decode(),
    }

    response = client.get("/workspaces/ws-alice", headers=headers("ws_api"))

    assert response.status_code == 200
    assert "credentials" not in response.json()["storage"]


@pytest.mark.parametrize(
    "selectors, expected",
    [
        (["s3:primary"], {"ws-alice-s3"}),
        (["s3:*"], {"ws-alice-s3"}),
        (["postgres:pg0", "s3:primary", "postgres:*"], {"ws-alice-pg0", "ws-alice-s3"}),
        (["*:pg0"], {"ws-alice-pg0", "external-catalog"}),
        (["custom:*"], {"external-catalog", "ws-alice-catalog"}),
        (["s3:missing"], set()),
        (["none"], set()),
        (["xxx", "yyy"], set()),
    ],
)
def test_selectors_only_read_matching_secrets(client: TestClient, connection_workspace: SimpleNamespace, selectors, expected) -> None:
    connection_workspace.connections.append(
        {
            "name": "pg0",
            "type": "custom",
            "ready": True,
            "secretRef": {"name": "external-catalog", "namespace": "runtime"},
        }
    )
    response = client.get(
        "/workspaces/ws-alice", params=[("resolve_connections", value) for value in selectors], headers=headers("ws_access")
    )

    assert response.status_code == 200
    assert {call.args[0] for call in connection_workspace.read_secret.call_args_list} == expected
    assert connection_workspace.read_secret.call_count == len(expected)
    if "external-catalog" in expected:
        connection_workspace.read_secret.assert_any_call("external-catalog", "runtime")


def test_default_resolves_only_primary_s3(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    response = client.get("/workspaces/ws-alice", headers=headers("ws_api"))

    assert response.status_code == 200
    data = response.json()
    assert data["storage"]["credentials"]["secret"] == S3_VALUE
    assert len(data["datalab"]["connections"]) == 7
    assert all("credentials" not in entry for entry in data["datalab"]["oauth2"])
    assert data["datalab"]["memberships"] == data["datalab"]["stores"] == data["datalab"]["sessions"] == []
    assert "resource_usage" not in data
    connection_workspace.read_secret.assert_called_once_with("ws-alice-s3", "workspace")


def test_unready_primary_s3_does_not_read_any_secret(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.connections[-1]["ready"] = False
    connection_workspace.secrets["ws-alice-datalab"] = connection_workspace.secrets["ws-alice-s3"]
    response = client.get("/workspaces/ws-alice", headers=headers("ws_api"))

    assert response.status_code == 200
    data = response.json()
    assert "credentials" not in data["storage"]
    assert data["status"] == "provisioning"
    assert data["datalab"]["connections"][-1]["resolution_error"] == "not_ready"
    connection_workspace.read_secret.assert_not_called()


def test_store_instances_keep_databases_with_the_same_name(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    connection_workspace.datalab.spec["databases"] = {
        "pg0": {"names": ["analytics"]},
        "pg1": {"names": ["analytics"]},
    }
    response = client.get("/workspaces/ws-alice?view=management&resolve_connections=none", headers=headers("ws_access"))
    assert response.status_code == 200
    stores = response.json()["datalab"]["stores"]
    assert {(store["type"], store["instance"], store["name"]) for store in stores} == {
        ("database", "pg0", "analytics"),
        ("database", "pg1", "analytics"),
        ("document", "docs", "docs"),
        ("cache", "cache", "cache"),
    }


def test_bucket_request_list_reports_kubernetes_access_error(
    client: TestClient, connection_workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "_extract_relevant_bucket_access_requests", _extract_relevant_bucket_access_requests)
    storage_api = mock.Mock()
    storage_api.get.side_effect = ApiException(status=403)
    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=headers("ws_access"))

    assert response.status_code == 502
    assert response.json()["detail"] == "Listing bucket access requests failed"


def test_dashboard_stores_use_only_published_instances(client: TestClient, connection_workspace: SimpleNamespace) -> None:
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=headers("ws_access"))
    assert response.status_code == 200
    assert {(item["type"], item["name"], item["instance"]) for item in response.json()["datalab"]["stores"]} == {
        ("database", "pg0", "pg0"),
        ("document", "mongo-docs", "mongo-docs"),
        ("cache", "redis-cache", "redis-cache"),
    }
    assert all("storage" not in item for item in response.json()["datalab"]["stores"])
    connection_workspace.connections.clear()
    response = client.get("/workspaces/ws-alice?resolve_connections=none", headers=headers("ws_access"))
    assert response.json()["datalab"]["stores"] == []


@pytest.mark.parametrize("failure", [None, 403, 404, 500, "transport", "invalid"])
def test_unreadable_connection_secret_does_not_stop_other_reads(client, connection_workspace, failure):
    def read_secret(name, _namespace) -> SimpleNamespace | None:
        if name == "ws-alice-pg0":
            if failure == "transport":
                message = "connection closed"
                raise OSError(message)
            if failure == "invalid":
                return SimpleNamespace(data={"password": "!invalid!"})
            if failure is not None:
                raise ApiException(status=failure)
            return None
        return connection_workspace.secrets.get(name)

    connection_workspace.read_secret.side_effect = read_secret
    response = client.get("/workspaces/ws-alice", params={"resolve_connections": "*"}, headers=headers("ws_admin"))
    assert response.status_code == 200
    entries = response.json()["datalab"]["connections"]
    failed = next(entry for entry in entries if entry["name"] == "pg0")
    assert failed.get("credentials") is None
    assert failed["resolution_error"]
    later = next(entry for entry in entries if entry["name"] == "mongo-docs")
    assert later["credentials"] == {"password": "test-value"}


@pytest.mark.parametrize("failure", [None, 403, 404, 500])
def test_unreadable_oauth_secret_does_not_stop_other_reads(client, connection_workspace, failure):
    def read_secret(name, _namespace) -> SimpleNamespace | None:
        if name == "ws-alice-oauth-client":
            if failure is not None:
                raise ApiException(status=failure)
            return None
        return connection_workspace.secrets.get(name)

    connection_workspace.read_secret.side_effect = read_secret
    response = client.get("/workspaces/ws-alice", params={"resolve_oauth2": "*"}, headers=headers("ws_admin"))
    assert response.status_code == 200
    entries = response.json()["datalab"]["oauth2"]
    assert entries[0].get("credentials") is None
    assert entries[0]["resolution_error"]
    assert entries[1]["credentials"]["clientID"] == "catalog-integration"
