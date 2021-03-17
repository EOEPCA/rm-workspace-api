from fastapi.testclient import TestClient
import pytest

from workspace_api import app


@pytest.fixture
def client():
    return TestClient(app)
