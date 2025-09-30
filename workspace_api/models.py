# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    CONTRIBUTOR = "contributor"


class BucketPermission(str, enum.Enum):
    OWNER = "owner"
    READ_WRITE = "readwrite"
    READ_ONLY = "readonly"
    WRITE_ONLY = "writeonly"
    NONE = "none"


class WorkspaceStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    READY = "ready"
    UNKNOWN = "unknown"


def _coerce_utc(dt: datetime | str | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        s = dt.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=dt.tzinfo or UTC).astimezone(UTC)


def _is_s3_bucket_name(name: str) -> bool:
    if not (3 <= len(name) <= 63):
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-.")
    if not set(name) <= allowed:
        return False
    if name[0] in ".-" or name[-1] in ".-":
        return False
    return not (".." in name or ".-" in name or "-." in name)


def _validate_bucket_name(v: str) -> str:
    v2 = (v or "").strip()
    if not _is_s3_bucket_name(v2):
        msg = "Invalid S3 bucket name."
        raise ValueError(msg)
    return v2


def _validate_bucket_list(values: list[str]) -> list[str]:
    return [_validate_bucket_name(b) for b in values]


class Membership(BaseModel):
    """A users membership in a workspace with assigned role and creation time."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace membership entry."})

    member: str = Field(..., description="The username of the member.")
    role: MembershipRole = Field(..., description="The role of the member.")
    creation_timestamp: datetime | None = Field(..., description="When the membership was created (UTC, RFC3339).")

    @field_validator("member", mode="before")
    @classmethod
    def _strip_member(cls, v: str) -> str:
        v2 = (v or "").strip()
        if not v2:
            msg = "must not be empty"
            raise ValueError(msg)
        return v2

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)


class BucketAccessRequest(BaseModel):
    """Represents either an outbound access request or an inbound grant record."""

    model_config = ConfigDict(
        json_schema_extra={"description": "Bucket access request/grant entry."},
        validate_assignment=True,
    )

    workspace: str = Field(..., description="Workspace receiving or requesting access.")
    bucket: str = Field(..., description="Target bucket.")
    permission: BucketPermission = Field(..., description="Requested or granted permission.")
    request_timestamp: datetime | None = Field(..., description="When the request was issued (UTC, RFC3339).")
    grant_timestamp: datetime | None = Field(None, description="When the request was granted (UTC, RFC3339).")
    denied_timestamp: datetime | None = Field(None, description="When the request was denied (UTC, RFC3339).")

    @field_validator("workspace", "bucket", mode="before")
    @classmethod
    def _strip_required_strings(cls, v: str) -> str:
        v2 = (v or "").strip()
        if not v2:
            msg = "must not be empty"
            raise ValueError(msg)
        return v2

    @field_validator("bucket")
    @classmethod
    def _check_bucket_name(cls, v: str) -> str:
        return _validate_bucket_name(v)

    @field_validator("request_timestamp", "grant_timestamp", "denied_timestamp", mode="before")
    @classmethod
    def _parse_iso_dt(cls, v: str | datetime | None) -> datetime | None:
        if v is None or isinstance(v, datetime):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            elif "+" not in s and "-" not in s[10:]:
                s = s + "+00:00"
            try:
                return datetime.fromisoformat(s)
            except ValueError as e:
                msg = f"Invalid datetime string: {v}"
                raise ValueError(msg) from e
        return v

    @field_validator("request_timestamp", "grant_timestamp", "denied_timestamp", mode="after")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)


class WorkspaceCreate(BaseModel):
    """Payload for creating a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace creation request."})

    preferred_name: str = Field("", description="User-provided preferred name; will be slugified and prefixed.")
    default_owner: str = Field("", description="Default owner username for the workspace.")


class WorkspaceEdit(BaseModel):
    """Patch-style edit payload for a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace edit (patch) request."})

    add_members: list[str] = Field(default_factory=list, description="Members to add.")
    add_extra_buckets: list[str] = Field(default_factory=list, description="Buckets to add.")
    patch_bucket_access_requests: list[BucketAccessRequest] = Field(
        default_factory=list,
        description="Bucket access requests/grants to upsert. Each entry MUST have workspace, bucket, and request_timestamp.",
    )

    @field_validator("add_members")
    @classmethod
    def _dedup_members(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for m in v:
            m2 = (m or "").strip()
            if m2 and m2 not in seen:
                seen.add(m2)
                out.append(m2)
        return out

    @field_validator("add_extra_buckets")
    @classmethod
    def _check_buckets(cls, v: list[str]) -> list[str]:
        return _validate_bucket_list(v)

    @field_validator("patch_bucket_access_requests")
    @classmethod
    def _require_min_fields_and_dedup(cls, items: list[BucketAccessRequest]) -> list[BucketAccessRequest]:
        deduped: dict[tuple[str, str, datetime], BucketAccessRequest] = {}
        for i, r in enumerate(items):
            if not r.workspace or not r.bucket or r.request_timestamp is None:
                msg = f"patch_bucket_access_requests[{i}] must set workspace, bucket, request_timestamp"
                raise ValueError(msg)
            key = (r.workspace, r.bucket, r.request_timestamp)
            deduped[key] = r
        return list(deduped.values())


class Credentials(BaseModel):
    """S3-compatible credentials for a workspace-owned bucket."""

    model_config = ConfigDict(json_schema_extra={"description": "S3 credentials for the workspace."})

    bucketname: str = Field(..., description="The name of the S3 bucket.")
    access: str = Field(..., description="The access key for the S3 storage.")
    secret: str = Field(..., description="The secret key for the S3 storage.")
    endpoint: str = Field(..., description="The S3 API endpoint URL.")
    region: str = Field(..., description="The S3 region.")


class ContainerRegistryCredentials(BaseModel):
    """Credentials for authenticating against a container registry."""

    model_config = ConfigDict(json_schema_extra={"description": "Container registry credentials."})

    username: str = Field(..., description="Registry username.")
    password: SecretStr = Field(..., description="Registry password.", json_schema_extra={"writeOnly": True})

    def base64_encode_as_single_string(self) -> str:
        pw = self.password.get_secret_value()
        return base64.b64encode(f"{self.username}:{pw}".encode()).decode()


class Workspace(BaseModel):
    """Workspace view model with metadata, buckets, credentials, and access state."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace resource representation."})

    name: str = Field(..., description="Unique, system-generated name.")
    creation_timestamp: datetime | None = Field(None, description="Creation timestamp of the S3 credentials secret.")
    version: str | None = Field(None, description="Resource version for optimistic locking.")
    status: WorkspaceStatus = Field(..., description="Current lifecycle status.")
    bucket: str | None = Field(None, description="Primary/default S3 bucket.")
    extra_buckets: list[str] = Field(default_factory=list, description="Extra buckets.")
    credentials: Credentials | None = Field(None, description="S3 credentials (bucket, keys, endpoint, region).")
    container_registry: ContainerRegistryCredentials | None = Field(None, description="Credentials for the workspace's container registry.")
    memberships: list[Membership] = Field(default_factory=list, description="Detailed membership entries.")
    bucket_access_requests: list[BucketAccessRequest] = Field(
        default_factory=list,
        description="Bucket access requests/grants associated with the workspace.",
    )

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)

    @field_validator("bucket")
    @classmethod
    def _bucket_single(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_bucket_name(v)

    @field_validator("extra_buckets")
    @classmethod
    def _bucket_lists(cls, v: list[str]) -> list[str]:
        return _validate_bucket_list(v)


class Endpoint(BaseModel):
    """Published endpoint of an exposed service within a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Exposed service endpoint."})

    id: str = Field(..., description="Unique identifier.")
    url: str = Field(..., description="Public URL of the exposed service.")
    creation_timestamp: datetime | None = Field(..., description="When the endpoint was created (UTC).")

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)
