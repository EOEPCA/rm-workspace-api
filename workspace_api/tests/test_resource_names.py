# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import pytest

from workspace_api.tests.test_views import _dev_token


@pytest.mark.parametrize("name", ["a" * 31, "Upper", "a.b", "a_b", "-demo", "demo-"])
@pytest.mark.parametrize("resource", ["workspace", "session", "store", "bucket", "profile", "namespace"])
def test_invalid_resource_names_return_validation_errors(client, name, resource):
    endpoint, payload = {
        "workspace": ("/workspaces", {"preferred_name": name}),
        "session": ("/workspaces/ws-alice/sessions", {"name": name}),
        "store": ("/workspaces/ws-alice", {"add_stores": [{"name": name, "type": "database"}]}),
        "bucket": ("/workspaces/ws-alice", {"add_buckets": [{"name": name}]}),
        "profile": ("/workspaces/ws-alice/vclusters/vc0/groups", {"name": name, "namespace": "analysis", "role": "edit"}),
        "namespace": ("/workspaces/ws-alice/vclusters/vc0/groups", {"namespace": name, "role": "edit"}),
    }[resource]
    response = client.request(
        "PUT" if resource in {"store", "bucket"} else "POST",
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {_dev_token({'workspace-api': {'roles': ['admin']}})}"},
    )
    assert response.status_code == 422
