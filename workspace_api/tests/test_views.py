import base64
from http import HTTPStatus
from unittest import mock

from fastapi.testclient import TestClient
import kubernetes.client.rest
from kubernetes import client as k8s_client
import pytest
import requests
import requests.exceptions

from workspace_api import config
from workspace_api.views import (
    WorkspaceStatus,
    wait_for_namespace_secret,
    workspace_name_from_preferred_name,
    deploy_helm_releases,
)


@pytest.fixture(autouse=True)
def mock_k8s_base():
    with mock.patch(
        "workspace_api.views.current_namespace",
        return_value="some-namespace",
    ):
        yield


@pytest.fixture()
def mock_read_namespace():
    # NOTE: if preferred name is a status, we mock the respective behavior
    def new_read_namespace(name: str, **kwargs):
        if any(name.endswith(s.value) for s in WorkspaceStatus):
            return {}
        else:
            raise kubernetes.client.rest.ApiException(status=HTTPStatus.NOT_FOUND)

    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.read_namespace",
        side_effect=new_read_namespace,
    ):
        yield


@pytest.fixture()
def mock_dynamic_client_apply():
    with mock.patch("workspace_api.views.DynamicClient") as mocker:
        yield mocker
        # "workspace_api.views.DynamicClient.resources.get.server_side_apply",


@pytest.fixture()
def mock_read_secret():
    def new_read_namespaced_secret(name: str, namespace: str, **kwargs):
        if name == "container-registry-admin":
            return k8s_client.V1Secret(data={"username": "", "password": ""})
        elif name == "container-registry":
            return k8s_client.V1Secret(
                data={
                    "username": base64.b64encode(b"container-registry-user"),
                    "password": "",
                }
            )
        elif name == config.UMA_CLIENT_SECRET_NAME:
            return k8s_client.V1Secret(data={"uma": "dW1h"})
        elif not namespace.endswith(WorkspaceStatus.provisioning.value):
            return k8s_client.V1Secret(data={"key": "eW91bGxuZXZlcmd1ZXNz"})
        else:
            raise kubernetes.client.rest.ApiException(status=HTTPStatus.NOT_FOUND)

    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.read_namespaced_secret",
        side_effect=new_read_namespaced_secret,
    ):
        yield


@pytest.fixture()
def mock_create_secret():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.create_namespaced_secret"
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_create_custom_object():
    with mock.patch(
        "workspace_api.views.k8s_client.CustomObjectsApi.create_namespaced_custom_object"
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_create_namespace():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.create_namespace"
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_delete_namespace():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.delete_namespace"
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_read_config_map():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.read_namespaced_config_map",
        return_value=k8s_client.V1ConfigMap(
            data={
                "hr1.yaml": """
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: resource-guard
  namespace: rm
spec:
  chart: null
  values:
    namespace: {{ workspace_name }}
"""
            },
        ),
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
def mock_patch_config_map():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.patch_namespaced_config_map",
        return_value={},
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret():
    return k8s_client.V1Secret(
        data={
            "access": "",
            "bucketname": "",
            "projectid": "",
            "secret": base64.b64encode(b"supersecret"),
        }
    )


@pytest.fixture()
def mock_wait_for_secret(mock_secret):
    with mock.patch(
        "workspace_api.views.wait_for_namespace_secret",
        return_value=mock_secret,
    ):
        yield


@pytest.fixture()
def mock_post_harbor_api():
    with mock.patch("requests.post") as mocker:
        yield mocker


def test_create_workspace_invents_name_if_missing(
    client: TestClient,
    mock_read_namespace,
    mock_create_custom_object,
    mock_create_secret,
    mock_read_secret,
    mock_post_harbor_api,
    mock_create_namespace,
    mock_wait_for_secret,
):
    response = client.post("/workspaces", json={})

    assert response.status_code == HTTPStatus.CREATED
    assert len(response.json()["name"]) > 10
    assert response.json()["name"].startswith(config.PREFIX_FOR_NAME)


def test_create_workspace_invents_name_invalid_if_no_proper_name_given(
    client: TestClient,
    mock_read_namespace,
    mock_create_custom_object,
    mock_create_secret,
    mock_read_secret,
    mock_post_harbor_api,
    mock_create_namespace,
    mock_wait_for_secret,
):
    response = client.post("/workspaces", json={"preferred_name": "'"})

    assert response.status_code == HTTPStatus.CREATED
    assert len(response.json()["name"]) > 10
    assert response.json()["name"].startswith(config.PREFIX_FOR_NAME)


def test_create_workspace_returns_sanitized_name(
    client: TestClient,
    mock_read_namespace,
    mock_create_custom_object,
    mock_create_namespace,
    mock_read_secret,
    mock_create_secret,
    mock_post_harbor_api,
    mock_wait_for_secret,
):
    response = client.post(
        "/workspaces",
        json={"preferred_name": "-as-df^&*-"},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        "name": f"{config.PREFIX_FOR_NAME}-as-df",
    }


def test_create_workspace_checks_for_name_collisions(
    client: TestClient, mock_read_namespace
):
    response = client.post(
        "/workspaces",
        json={"preferred_name": "ready"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_create_workspace_creates_namespace_and_bucket_and_starts_phase_2(
    client: TestClient,
    mock_read_namespace,
    mock_create_custom_object,
    mock_read_secret,
    mock_create_secret,
    mock_create_namespace,
    mock_wait_for_secret,
    mock_post_harbor_api,
    mock_read_config_map,
    mock_dynamic_client_apply,
):
    name = "tklayafg"
    client.post("/workspaces", json={"preferred_name": name})

    assert len(mock_create_custom_object.mock_calls) == 1

    # create ns
    mock_create_namespace.assert_called_once()

    # create bucket
    params = mock_create_custom_object.mock_calls[0][2]
    assert params["body"]["kind"] == "Bucket"
    assert name in params["body"]["spec"]["bucketName"]

    # create helm releases
    assert mock_dynamic_client_apply.mock_calls

    # create uma secret
    assert (
        base64.b64decode(
            mock_create_secret.mock_calls[0][2]["body"].data["uma"]
        ).decode()
        == "uma"
    )

    # create harbor credentials via api
    mock_post_harbor_api.assert_called_once()
    assert name in mock_post_harbor_api.mock_calls[0][2]["json"]["username"]

    # store harbor credentials in secret
    assert (
        name
        in base64.b64decode(
            mock_create_secret.mock_calls[1][2]["body"].data["username"]
        ).decode()
    )


def test_deploy_hrs_deploys_from_templated_config_map(
    mock_read_config_map,
    mock_dynamic_client_apply,
    mock_secret,
):
    deploy_helm_releases(
        workspace_name="a",
        secret=mock_secret,
        default_owner="me",
    )

    hr_body = mock_dynamic_client_apply.mock_calls[-1].kwargs["body"]
    assert hr_body["spec"]["values"]["namespace"] == "a"


def test_create_repository_in_container_registry_calls_harbor(
    client, mock_post_harbor_api
):
    response = client.post(
        f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}"
        "/create-container-registry-repository",
        json={"repository_name": "asdf"},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert mock_post_harbor_api.mock_calls[0][2]["json"]["project_name"] == "asdf"
    assert mock_post_harbor_api.mock_calls[2][2]["json"]["role_id"] == 2


def test_create_repository_in_container_registry_returns_error_on_conflict(client):
    with mock.patch(
        "requests.post",
        side_effect=requests.exceptions.HTTPError(
            response=mock.MagicMock(status_code=HTTPStatus.CONFLICT)
        ),
    ):
        response = client.post(
            f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}"
            "/create-container-registry-repository",
            json={"repository_name": "asdf"},
        )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_create_repository_in_container_registry_forwards_error_on_bad_request(client):
    response = requests.Response()
    response.status_code = HTTPStatus.BAD_REQUEST
    response.json = lambda: {
        "errors": [{"code": "BAD_REQUEST", "message": "project name bad"}]
    }
    with mock.patch(
        "requests.post",
        side_effect=requests.exceptions.HTTPError(response=response),
    ):
        response = client.post(
            f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}"
            "/create-container-registry-repository",
            json={"repository_name": "asdf"},
        )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "name bad" in response.text


def test_grant_access_to_repository_calls_harbor(client, mock_post_harbor_api):
    response = client.post(
        "/grant-access-to-container-registry-repository",
        json={"repository_name": "asdf", "username": "jkl"},
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert "asdf" in mock_post_harbor_api.mock_calls[0][1][0]
    assert (
        mock_post_harbor_api.mock_calls[0][2]["json"]["member_user"]["username"]
        == "jkl"
    )


def test_get_workspace_returns_not_found_if_not_found(
    client: TestClient, mock_read_namespace
):
    response = client.get(
        f"/workspaces/{workspace_name_from_preferred_name('does-not-exist')}"
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_workspace_returns_provisioning(
    client: TestClient,
    mock_read_namespace,
    mock_read_secret,
):
    response = client.get(
        "/workspaces/"
        + workspace_name_from_preferred_name(WorkspaceStatus.provisioning.value)
    )
    assert response.json()["status"] == "provisioning"


def test_get_workspace_returns_ready(
    client: TestClient,
    mock_read_namespace,
    mock_read_secret,
    mock_list_ingress,
    mock_read_config_map,
):
    response = client.get(
        f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}"
    )
    assert response.json()["status"] == "ready"
    assert response.json()["endpoints"] == [{"id": "myingress", "url": "example.com"}]
    assert response.json()["storage"] == {
        "credentials": {
            "key": "youllneverguess",
            "endpoint": "",
            "region": "",
        },
        # "quota_in_mb": 123,
    }
    assert (
        response.json()["container_registry"]["username"] == "container-registry-user"
    )


def test_get_workspace_only_works_on_prefixed_path(client: TestClient):
    response = client.get("/workspaces/notaprefix")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_delete_workspaces_only_works_on_prefixed_path(
    client: TestClient, mock_delete_namespace
):
    response = client.delete("/workspaces/notaprefix")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    mock_delete_namespace.assert_not_called()


def test_workspaces_can_be_deleted(client: TestClient, mock_delete_namespace):
    response = client.delete(
        f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}"
    )
    assert response.status_code == HTTPStatus.NO_CONTENT
    mock_delete_namespace.assert_called_once()


def test_quota_in_mb_can_be_updated(client: TestClient, mock_patch_config_map):
    new_quota = 481658
    response = client.patch(
        f"/workspaces/{workspace_name_from_preferred_name(WorkspaceStatus.ready.value)}",
        json={"storage": {"quota_in_mb": new_quota}},
    )
    assert response.status_code == HTTPStatus.NO_CONTENT
    mock_patch_config_map.assert_called_once()


def test_wait_for_secret_terminates_on_secret():
    fake_events = [
        {
            "type": "ADDED",
            "object": k8s_client.V1Secret(
                metadata=k8s_client.V1ObjectMeta(name=config.WORKSPACE_SECRET_NAME)
            ),
        },
    ]

    with mock.patch(
        "workspace_api.views.kubernetes.watch.Watch.stream",
        return_value=fake_events,
    ):
        secret = wait_for_namespace_secret("test")

    assert secret


def test_wait_for_secret_does_not_terminate_if_wrong_secret():
    fake_events = [
        {
            "type": "ADDED",
            "object": k8s_client.V1Secret(
                metadata=k8s_client.V1ObjectMeta(name="other")
            ),
        },
    ]

    with mock.patch(
        "workspace_api.views.kubernetes.watch.Watch.stream",
        return_value=fake_events,
    ):
        with pytest.raises(Exception):
            wait_for_namespace_secret("test")
