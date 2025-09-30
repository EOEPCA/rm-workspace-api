# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
from collections.abc import Generator
from http import HTTPStatus
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from kubernetes import client as k8s_client  # type: ignore[import-untyped]


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


def test_get_workspace_only_works_on_prefixed_path(client: TestClient) -> None:
    response = client.get("/workspaces/notaprefix")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
