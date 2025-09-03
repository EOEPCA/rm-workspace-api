# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # noqa: S101
