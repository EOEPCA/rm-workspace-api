# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi.testclient import TestClient

from workspace_api import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
