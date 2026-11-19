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
from httpx import Response

from workspace_api import config, views
from workspace_api.tests.test_views import _dev_token

DATA_URL = "https://ws-alice.lab.example.org/"
SESSION_URL = "https://ws-alice-notebook.lab.example.org/"


@pytest.fixture
def endpoint_workspace(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    datalab = SimpleNamespace(
        metadata=SimpleNamespace(creationTimestamp=None, resourceVersion="1"),
        spec={"endpoints": [{"name": "spec-only", "url": DATA_URL, "ready": True}]},
        status={
            "conditions": [{"type": "Ready", "status": "True"}],
            "sessions": [{"name": "notebook", "state": "started", "phase": "Running", "url": SESSION_URL}],
        },
    )
    monkeypatch.setattr(views, "_get_cr", lambda _api, kind, *_args, **_kwargs: datalab if kind == views.KIND_DATALAB else None)
    monkeypatch.setattr(config, "UI_MODE", "ui")
    monkeypatch.setattr(views, "templates", Jinja2Templates(directory=Path("workspace_ui/luigi-shell")))
    read_secret = mock.Mock()
    monkeypatch.setattr(views, "fetch_secret", read_secret)
    return SimpleNamespace(datalab=datalab, read_secret=read_secret)


def _workspace_response(client: TestClient, *, html: bool = False) -> Response:
    return client.get(
        "/workspaces/ws-alice?resolve_connections=none",
        headers={"Authorization": f"Bearer {_dev_token()}", "Accept": "text/html" if html else "application/json"},
    )


def _sidebar_links(response: Response) -> list[dict[str, str]]:
    assert response.status_code == 200
    match = re.search(r"const endpointsData = '([^']+)'", response.text)
    assert match is not None
    return json.loads(base64.b64decode(match[1]))


def test_ready_published_endpoints_join_session_links(client: TestClient, endpoint_workspace: SimpleNamespace) -> None:
    endpoints = [
        {"name": "data", "url": DATA_URL, "ready": True},
        {"name": "Catalog", "url": "https://catalog.example.org/browse?view=team#items", "ready": True},
        {"name": "pending", "url": "https://pending.example.org/", "ready": False},
    ]
    endpoint_workspace.datalab.status["endpoints"] = endpoints

    response = _workspace_response(client)
    assert response.status_code == 200
    assert response.json()["datalab"]["endpoints"] == endpoints
    assert response.json()["status"] == "ready"
    assert _sidebar_links(_workspace_response(client, html=True)) == [
        {"id": "Data", "url": DATA_URL},
        {"id": "Catalog", "url": "https://catalog.example.org/browse?view=team#items"},
        {"id": "Datalab (notebook)", "url": SESSION_URL},
    ]
    endpoint_workspace.read_secret.assert_not_called()


@pytest.mark.parametrize(
    "status",
    [
        {},
        {"endpoints": None},
        {"endpoints": []},
        {"endpoints": {"name": "data", "url": DATA_URL, "ready": True}},
    ],
)
def test_absent_or_invalid_endpoints_do_not_break_workspace_links(
    client: TestClient, endpoint_workspace: SimpleNamespace, status: dict
) -> None:
    endpoint_workspace.datalab.status.update(status)

    response = _workspace_response(client)
    assert response.status_code == 200
    assert response.json()["datalab"]["endpoints"] == []
    assert response.json()["status"] == "ready"
    assert _sidebar_links(_workspace_response(client, html=True)) == [{"id": "Datalab (notebook)", "url": SESSION_URL}]


def test_invalid_endpoint_metadata_adds_no_links(client: TestClient, endpoint_workspace: SimpleNamespace) -> None:
    endpoint_workspace.datalab.status["endpoints"] = [
        None,
        "invalid",
        {},
        {"name": " ", "url": DATA_URL, "ready": True},
        {"name": 1, "url": DATA_URL, "ready": True},
        {"name": "missing-ready", "url": DATA_URL},
        {"name": "text-ready", "url": DATA_URL, "ready": "true"},
        {"name": "numeric-ready", "url": DATA_URL, "ready": 1},
        {"name": "missing-url", "ready": True},
        {"name": "unsafe-url", "url": "javascript:alert(1)", "ready": True},
        {"name": "relative-url", "url": "/data", "ready": True},
        {"name": "invalid-host", "url": "https://[invalid/", "ready": True},
        {"name": "credentials-url", "url": "https://user:password@example.org/", "ready": True},
    ]

    response = _workspace_response(client)
    assert response.status_code == 200
    endpoints = response.json()["datalab"]["endpoints"]
    assert all(endpoint["ready"] is False for endpoint in endpoints)
    assert response.json()["status"] == "ready"
    assert _sidebar_links(_workspace_response(client, html=True)) == [{"id": "Datalab (notebook)", "url": SESSION_URL}]
