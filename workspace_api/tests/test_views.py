import base64
from http import HTTPStatus
from unittest import mock

from fastapi.testclient import TestClient
import kubernetes.client.rest
from kubernetes import client as k8s_client
import pytest

from workspace_api import config
from workspace_api.views import (
    WorkspaceStatus,
    install_workspace_phase2,
    wait_for_namespace_secret,
    workspace_name_from_preferred_name,
)


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
def mock_read_secret():
    def new_read_namespaced_secret(name: str, namespace: str, **kwargs):
        if not namespace.endswith(WorkspaceStatus.provisioning.value):
            return k8s_client.V1Secret(data={"key": "eW91bGxuZXZlcmd1ZXNz"})
        else:
            raise kubernetes.client.rest.ApiException(status=HTTPStatus.NOT_FOUND)

    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.read_namespaced_secret",
        side_effect=new_read_namespaced_secret,
    ):
        yield


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
def mock_list_ingress():
    with mock.patch(
        "workspace_api.views.k8s_client.ExtensionsV1beta1Api.list_namespaced_ingress",
        return_value=k8s_client.ExtensionsV1beta1IngressList(
            items=[
                k8s_client.ExtensionsV1beta1Ingress(
                    metadata=k8s_client.V1ObjectMeta(name="myingress"),
                    spec=k8s_client.ExtensionsV1beta1IngressSpec(
                        rules=[
                            k8s_client.ExtensionsV1beta1IngressRule(host="example.com")
                        ]
                    ),
                )
            ]
        ),
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_read_config_map():
    with mock.patch(
        "workspace_api.views.k8s_client.CoreV1Api.read_namespaced_config_map",
        return_value=k8s_client.V1ConfigMap(
            data={
                "stuff": "idontcare",
                "quota_in_mb": "123",
            }
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
def mock_wait_for_secret():
    secret = k8s_client.V1Secret(
        data={
            "access": "",
            "bucketname": "",
            "secret": base64.b64encode(b"supersecret"),
            # actual secrets also have 'projectid', but we don't use that now
        }
    )
    with mock.patch(
        "workspace_api.views.wait_for_namespace_secret",
        return_value=secret,
    ):
        yield


def test_create_workspace_invents_name_if_missing(
    client: TestClient,
    mock_read_namespace,
    mock_create_custom_object,
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
    mock_create_namespace,
    mock_wait_for_secret,
):
    name = "tklayafg"
    client.post("/workspaces", json={"preferred_name": name})

    assert len(mock_create_custom_object.mock_calls) == 2

    # create ns
    mock_create_namespace.assert_called_once()

    # create bucket
    params = mock_create_custom_object.mock_calls[0].kwargs
    assert params["body"]["kind"] == "Bucket"
    assert name in params["body"]["spec"]["bucketName"]

    # create helm release
    params = mock_create_custom_object.mock_calls[1].kwargs
    assert name in params["namespace"]
    assert params["body"]["kind"] == "HelmRelease"
    assert name in params["body"]["metadata"]["namespace"]


def test_install_workspace_phase2_sets_values(
    mock_wait_for_secret,
    mock_create_custom_object,
):
    install_workspace_phase2("test")

    mock_create_custom_object.assert_called_once()
    values = mock_create_custom_object.mock_calls[0].kwargs["body"]["spec"]["values"]
    assert values["vs"]["ingress"]["hosts"][0]["host"].startswith("data-acc")
    assert (
        values["vs"]["config"]["objectStorage"]["data"]["secret_access_key"]
        == "supersecret"
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
        "credentials": {"key": "youllneverguess"},
        # "quota_in_mb": 123,
    }


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
