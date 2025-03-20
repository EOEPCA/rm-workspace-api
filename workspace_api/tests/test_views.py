import base64
from http import HTTPStatus
from unittest import mock

from fastapi.testclient import TestClient
from kubernetes import client as k8s_client
import pytest


@pytest.fixture()
def mock_remote_backend_harbor():
    with mock.patch(
        "workspace_api.config.HARBOR_URL",
        new="https://example_harbor.com",
    ):
        yield


@pytest.fixture()
def mock_create_secret():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.create_namespaced_secret"
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_list_ingress():
    with mock.patch(
        "workspace_api.views.k8s_client.NetworkingV1Api.list_namespaced_ingress",
        return_value=k8s_client.V1IngressList(
            items=[
                k8s_client.V1Ingress(
                    metadata=k8s_client.V1ObjectMeta(name="myingress"),
                    spec=k8s_client.V1IngressSpec(
                        rules=[k8s_client.V1IngressRule(host="example.com")]
                    ),
                )
            ]
        ),
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret():
    return k8s_client.V1Secret(
        data={
            "access": "",
            "bucketname": "",
            "secret": base64.b64encode(b"supersecret"),
        }
    )


@pytest.fixture()
def mock_post_harbor_api(
    requests_mock,
    mock_remote_backend_harbor: None,
):
    return requests_mock.post("https://example_harbor.com/api/v2.0/users")


@pytest.fixture()
def mock_post_harbor_projects_members_api(
    requests_mock,
    mock_remote_backend_harbor: None,
):
    return requests_mock.post(
        "https://example_harbor.com/api/v2.0/projects/asdf/members"
    )


@pytest.fixture()
def mock_post_harbor_repository_api(
    requests_mock,
    mock_remote_backend_harbor: None,
):
    return requests_mock.post("https://example_harbor.com/api/v2.0/projects")


def test_get_workspace_only_works_on_prefixed_path(client: TestClient):
    response = client.get("/workspaces/notaprefix")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
