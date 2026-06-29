# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from workspace_api import views
from workspace_api.models import Bucket, BucketLifecycleRule, BucketLifecycleRuleMode
from workspace_api.views import _bucket_lifecycle_rules_from_provider, _bucket_lifecycle_rules_to_provider


def _dev_token() -> str:
    def enc(obj: object) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = enc({"alg": "none", "typ": "JWT"})
    payload = enc(
        {
            "preferred_username": "test",
            "resource_access": {"workspace-api": {"roles": ["admin"]}},
        }
    )
    return f"{header}.{payload}."


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_dev_token()}"}


def test_bucket_lifecycle_rule_validates_provider_shape() -> None:
    rule = BucketLifecycleRule(target="tmp/*", mode=BucketLifecycleRuleMode.DELETE, min_age="2w", at=None)

    assert rule.target == "tmp/*"
    assert rule.mode == BucketLifecycleRuleMode.DELETE
    assert rule.min_age == "2w"

    with pytest.raises(ValueError, match="target"):
        BucketLifecycleRule(target="bad*path", mode=BucketLifecycleRuleMode.DELETE, min_age="1d", at=None)

    with pytest.raises(ValueError, match="exactly one"):
        BucketLifecycleRule(
            target="*",
            mode=BucketLifecycleRuleMode.DELETE,
            min_age="1d",
            at=datetime(2026, 5, 5, 20, 0, tzinfo=UTC),
        )


def test_bucket_lifecycle_rules_round_trip_provider_fields() -> None:
    rules = _bucket_lifecycle_rules_from_provider(
        {
            "lifecycleRules": [
                {"target": "*", "mode": "Notify", "at": "2026-05-05T20:00:00Z"},
            ]
        }
    )

    assert rules == [
        BucketLifecycleRule(
            target="*",
            mode=BucketLifecycleRuleMode.NOTIFY,
            min_age=None,
            at=datetime(2026, 5, 5, 20, 0, tzinfo=UTC),
        )
    ]
    assert _bucket_lifecycle_rules_to_provider(rules) == [{"target": "*", "mode": "Notify", "at": "2026-05-05T20:00:00+00:00"}]


def test_update_workspace_patches_bucket_lifecycle_rules(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = SimpleNamespace(
        spec={
            "principal": "ws-alice",
            "buckets": [
                {
                    "bucketName": "ws-alice-data",
                    "discoverable": True,
                    "lifecycleRules": [{"target": "old/*", "mode": "Notify", "minAge": "1d"}],
                }
            ],
            "bucketAccessRequests": [],
            "bucketAccessGrants": [],
        }
    )

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: None)

    response = client.put(
        "/workspaces/ws-alice",
        json={
            "add_memberships": [],
            "add_stores": [],
            "add_buckets": [
                {
                    "name": "ws-alice-data",
                    "discoverable": True,
                    "lifecycle_rules": [
                        {"target": "tmp/*", "mode": "Delete", "min_age": "2w"},
                        {"target": "archive/*", "mode": "Notify", "at": "2026-05-05T20:00:00Z"},
                    ],
                }
            ],
            "patch_bucket_access_requests": [],
        },
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    patch_body = storage_api.patch.call_args.kwargs["body"]
    assert patch_body["spec"]["buckets"][0]["lifecycleRules"] == [
        {"target": "tmp/*", "mode": "Delete", "minAge": "2w"},
        {"target": "archive/*", "mode": "Notify", "at": "2026-05-05T20:00:00+00:00"},
    ]


def test_update_workspace_keeps_lifecycle_rules_when_field_is_omitted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_api = mock.MagicMock()
    storage_api.get.return_value = SimpleNamespace(
        spec={
            "principal": "ws-alice",
            "buckets": [
                {
                    "bucketName": "ws-alice-data",
                    "discoverable": True,
                    "lifecycleRules": [{"target": "old/*", "mode": "Notify", "minAge": "1d"}],
                }
            ],
            "bucketAccessRequests": [],
            "bucketAccessGrants": [],
        }
    )

    monkeypatch.setattr(views, "_res_required", lambda *_args: storage_api)
    monkeypatch.setattr(views, "_res_optional", lambda *_args: None)

    response = client.put(
        "/workspaces/ws-alice",
        json={
            "add_memberships": [],
            "add_stores": [],
            "add_buckets": [{"name": "ws-alice-data", "discoverable": True}],
            "patch_bucket_access_requests": [],
        },
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    patch_body = storage_api.patch.call_args.kwargs["body"]
    assert patch_body["spec"]["buckets"][0]["lifecycleRules"] == [{"target": "old/*", "mode": "Notify", "minAge": "1d"}]


def test_bucket_model_deduplicates_lifecycle_rules_by_target() -> None:
    bucket = Bucket(
        name="ws-alice-data",
        discoverable=False,
        lifecycle_rules=[
            BucketLifecycleRule(target="tmp/*", mode=BucketLifecycleRuleMode.DELETE, min_age="1d", at=None),
            BucketLifecycleRule(target="tmp/*", mode=BucketLifecycleRuleMode.NOTIFY, min_age="2d", at=None),
        ],
        creation_timestamp=None,
    )

    assert bucket.lifecycle_rules == [BucketLifecycleRule(target="tmp/*", mode=BucketLifecycleRuleMode.DELETE, min_age="1d", at=None)]
