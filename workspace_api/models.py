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

from __future__ import annotations

import base64
import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
)

# ---------- Enums ----------


class MembershipRole(str, enum.Enum):
    """Role of a workspace member."""

    OWNER = "owner"
    CONTRIBUTOR = "contributor"


class BucketPermission(str, enum.Enum):
    """Access permissions for a bucket."""

    OWNER = "owner"
    READ_WRITE = "readwrite"
    READ_ONLY = "readonly"
    NONE = "none"


class WorkspaceStatus(str, enum.Enum):
    """Lifecycle status of a workspace."""

    PROVISIONING = "provisioning"
    READY = "ready"
    UNKNOWN = "unknown"


class ClusterStatus(str, enum.Enum):
    """Desired/actual status of a virtual cluster."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    AUTO = "auto"


# ---------- Helpers ----------


def _coerce_utc(dt: datetime | str | None) -> datetime | None:
    """Coerce datetimes (or ISO 8601 strings) to timezone-aware UTC."""
    if dt is None:
        return None
    if isinstance(dt, str):
        s = dt.strip()
        # Support trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            msg = f"Invalid datetime string: {dt}"
            raise ValueError(msg) from exc
    # If naive, assume UTC; always return aware UTC
    return dt.replace(tzinfo=dt.tzinfo or UTC).astimezone(UTC)


def _is_s3_bucket_name(name: str) -> bool:
    # Simple check (RFC-ish): 3-63 chars, lowercase, digits, dots, hyphens; no leading/trailing dot/hyphen, no ".."
    if not (3 <= len(name) <= 63):
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-.")
    if not set(name) <= allowed:
        return False
    if name[0] in ".-" or name[-1] in ".-":
        return False
    return not (".." in name or ".-" in name or "-." in name)


def _validate_bucket_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for b in values:
        b2 = b.strip()
        if not _is_s3_bucket_name(b2):
            msg = f"Invalid S3 bucket name: {b}"
            raise ValueError(msg)
        out.append(b2)
    return out


# ---------- Models ----------


class Membership(BaseModel):
    """Represents a membership between a user and a workspace."""

    member: str = Field(..., description="The username of the member.")
    role: MembershipRole = Field(..., description="The role of the member.")
    creation_timestamp: datetime = Field(..., description="When the membership was created (UTC).")

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        out = _coerce_utc(v)
        if out is None:
            msg = "Failed to coerce creation_timestamp to UTC."
            raise ValueError(msg)
        return out


class Bucket(BaseModel):
    """An S3-compatible bucket and the granted permission (if any)."""

    name: str = Field(..., description="Bucket name.")
    permission: BucketPermission | None = Field(None, description="Granted permission; None if not granted yet.")

    @field_validator("name")
    @classmethod
    def _bucket_name(cls, v: str) -> str:
        v2 = v.strip()
        if not _is_s3_bucket_name(v2):
            msg = "Invalid S3 bucket name."
            raise ValueError(msg)
        return v2


class BucketAccessRequest(BaseModel):
    """A request for access to a bucket."""

    workspace: str = Field(..., description="Requesting workspace.")
    bucket: str = Field(..., description="Requested bucket name.")
    permission: BucketPermission = Field(..., description="Requested permission.")
    request_timestamp: datetime | None = Field(None, description="When the request was issued (None if not issued).")
    grant_timestamp: datetime | None = Field(None, description="When the request was granted (None if not granted).")
    denied_timestamp: datetime | None = Field(None, description="When the request was denied (None if not denied).")

    @field_validator("bucket")
    @classmethod
    def _bucket_name(cls, v: str) -> str:
        v2 = v.strip()
        if not _is_s3_bucket_name(v2):
            msg = "Invalid S3 bucket name."
            raise ValueError(msg)
        return v2

    @field_validator("request_timestamp", "grant_timestamp", "denied_timestamp", mode="after")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)


class WorkspaceCreate(BaseModel):
    """Payload for creating a new workspace."""

    preferred_name: str = Field(
        "",
        description="User-provided preferred name; will be slugified and (optionally) prefixed.",
    )
    default_owner: str = Field("", description="Default owner username for the workspace.")


class WorkspaceEdit(BaseModel):
    """Payload for updating an existing workspace."""

    name: str = Field(..., description="Workspace to edit.")
    members: list[str] = Field(..., description="Definitive list of member usernames.")
    extra_buckets: list[str] = Field(default_factory=list, description="Additional S3 buckets for the workspace.")
    linked_buckets: list[str] = Field(default_factory=list, description="Linked S3 buckets from other workspaces.")
    bucket_access_requests: list[BucketAccessRequest] = Field(default_factory=list, description="Requested S3 buckets.")

    @field_validator("members")
    @classmethod
    def _dedup_members(cls, v: list[str]) -> list[str]:
        # Preserve order while deduplicating
        seen: set[str] = set()
        out: list[str] = []
        for m in v:
            m2 = m.strip()
            if m2 and m2 not in seen:
                seen.add(m2)
                out.append(m2)
        return out

    @field_validator("extra_buckets", "linked_buckets")
    @classmethod
    def _check_buckets(cls, v: list[str]) -> list[str]:
        return _validate_bucket_list(v)


class StorageCredentials(BaseModel):
    """Defines the specific set of credentials for S3-compatible storage."""

    bucketname: str = Field(..., description="The name of the S3 bucket.")
    access: str = Field(..., description="The access key for the S3 storage.")
    secret: str = Field(..., description="The secret key for the S3 storage.")
    endpoint: str = Field(..., description="The S3 API endpoint URL.")
    region: str = Field(..., description="The S3 region.")


class Storage(BaseModel):
    """Primary S3 storage for the workspace."""

    credentials: StorageCredentials = Field(..., description="S3 credentials (bucket, keys, endpoint, region).")
    buckets: list[str] = Field(default_factory=list, description="All S3 bucket names associated with the workspace.")

    @field_validator("buckets")
    @classmethod
    def _check_buckets(cls, v: list[str]) -> list[str]:
        return list(_validate_bucket_list(v))


class Cluster(BaseModel):
    """Virtual Kubernetes cluster associated with the workspace."""

    kubeconfig: SecretStr = Field(
        SecretStr(""), description="Kubeconfig file contents.", json_schema_extra={"writeOnly": True}
    )
    status: ClusterStatus = Field(..., description="Current cluster status.")


class ContainerRegistryCredentials(BaseModel):
    """Credentials for a container registry."""

    username: str = Field(..., description="Registry username.")
    password: SecretStr = Field(..., description="Registry password.", json_schema_extra={"writeOnly": True})

    def base64_encode_as_single_string(self) -> str:
        """Encodes username:password as base64 (for Docker auth fields)."""
        pw = self.password.get_secret_value()
        return base64.b64encode(f"{self.username}:{pw}".encode()).decode()


class Workspace(BaseModel):
    """A single workspace and all its components."""

    name: str = Field(..., description="Unique, system-generated name.")
    creation_timestamp: datetime | None = Field(
        None, description="Creation timestamp of the underlying Kubernetes object (UTC)."
    )
    version: str | None = Field(None, description="Resource version for optimistic locking.")
    status: WorkspaceStatus = Field(..., description="Current lifecycle status.")
    spec: Any | None = Field(None, description="Raw `spec` from the Kubernetes Workspace CR (debugging only).")
    storage: Storage | None = Field(None, description="Primary S3 storage, including credentials and buckets.")
    container_registry: ContainerRegistryCredentials | None = Field(
        None, description="Credentials for the workspace's container registry."
    )
    cluster: Cluster | None = Field(None, description="Details of the virtual Kubernetes cluster.")
    members: list[str] = Field(default_factory=list, description="Usernames of all members in the workspace.")

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)


class Endpoint(BaseModel):
    """A network endpoint (e.g., an Ingress) exposed by the workspace."""

    id: str = Field(..., description="Unique identifier (e.g., Ingress name).")
    url: str = Field(..., description="Public URL of the exposed service.")
    creation_timestamp: datetime = Field(..., description="When the endpoint was created (UTC).")

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        out = _coerce_utc(v)
        if out is None:
            msg = "Failed to coerce creation_timestamp to UTC."
            raise ValueError(msg)
        return out
