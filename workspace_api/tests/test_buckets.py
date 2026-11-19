# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from workspace_api import views
from workspace_api.models import Bucket, BucketLifecycleRule, BucketLifecycleRuleMode
from workspace_api.tests.test_views import _dev_token
from workspace_api.views import _bucket_lifecycle_rules_from_provider, _bucket_lifecycle_rules_to_provider


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_dev_token()}"}


def test_bucket_lifecycle_rule_rejects_invalid_target_and_schedule() -> None:
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


@pytest.mark.parametrize(
    "rules, expected",
    [
        (
            [
                {"target": "tmp/*", "mode": "Delete", "min_age": "2w"},
                {"target": "archive/*", "mode": "Notify", "at": "2026-05-05T20:00:00Z"},
            ],
            [
                {"target": "tmp/*", "mode": "Delete", "minAge": "2w"},
                {"target": "archive/*", "mode": "Notify", "at": "2026-05-05T20:00:00+00:00"},
            ],
        ),
        (None, [{"target": "old/*", "mode": "Notify", "minAge": "1d"}]),
    ],
)
def test_bucket_update_replaces_rules_only_when_supplied(client: TestClient, monkeypatch: pytest.MonkeyPatch, rules, expected) -> None:
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

    bucket = {"name": "ws-alice-data", "discoverable": True}
    if rules is not None:
        bucket["lifecycle_rules"] = rules
    response = client.put(
        "/workspaces/ws-alice",
        json={"add_buckets": [bucket]},
        headers=_auth_headers(),
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    patch_body = storage_api.patch.call_args.kwargs["body"]
    assert patch_body["spec"]["buckets"][0]["lifecycleRules"] == expected


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
