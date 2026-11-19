# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from workspace_api import app, config, views


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def ui_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "UI_MODE", "ui")
    monkeypatch.setattr(views, "templates", Jinja2Templates(directory=Path(__file__).parents[2] / "workspace_ui" / "luigi-shell"))
