# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import pytest

from workspace_api import views
from workspace_api.models import validate_resource_name
from workspace_api.tests.test_views import _dev_token


@pytest.mark.parametrize("resource", ["workspace", "session", "store", "bucket", "profile", "namespace"])
def test_long_resource_names_are_rejected_before_cluster_access(client, monkeypatch, resource):
    name = "a" * 31
    endpoint, payload, field = {
        "workspace": (
            "/workspaces",
            {"preferred_name": name, "storage": {"composition": "storage-minio"}, "datalab": {"composition": "datalab-educates"}},
            ["preferred_name"],
        ),
        "session": ("/workspaces/ws-alice/sessions", {"name": name}, ["name"]),
        "store": ("/workspaces/ws-alice", {"add_stores": [{"name": name, "type": "database"}]}, ["add_stores"]),
        "bucket": ("/workspaces/ws-alice", {"add_buckets": [{"name": name}]}, ["add_buckets"]),
        "profile": (
            "/workspaces/ws-alice/vclusters/vc0/groups",
            {"name": name, "namespace": "analysis", "role": "edit"},
            ["name"],
        ),
        "namespace": ("/workspaces/ws-alice/vclusters/vc0/groups", {"namespace": name, "role": "edit"}, ["namespace"]),
    }[resource]

    def forbidden(*_args: object) -> None:
        pytest.fail("Invalid names must be rejected before cluster access")

    monkeypatch.setattr(views, "_res_optional", forbidden)
    response = client.request(
        "PUT" if resource in {"store", "bucket"} else "POST",
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {_dev_token({'workspace-api': {'roles': ['admin']}})}"},
    )
    assert response.status_code == 422
    assert ["body", *field] in [error["loc"] for error in response.json()["detail"]]


def test_resource_name_rules() -> None:
    for name in ("a", "1", "team-blue", "a" * 30):
        assert validate_resource_name(name) == name
    for name in ("", "a" * 31, "Upper", "a.b", "a_b", "-demo", "demo-"):
        with pytest.raises(ValueError, match="1-30 lowercase"):
            validate_resource_name(name)
