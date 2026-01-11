# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, field_validator


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"


class BucketPermission(str, enum.Enum):
    READ_WRITE = "ReadWrite"
    READ_ONLY = "ReadOnly"
    WRITE_ONLY = "WriteOnly"
    NONE = "None"


class UserPermission(str, enum.Enum):
    VIEW_BUCKET_CREDENTIALS = "VIEW_BUCKET_CREDENTIALS"
    VIEW_MEMBERS = "VIEW_MEMBERS"
    VIEW_BUCKETS = "VIEW_BUCKETS"
    VIEW_DATABASES = "VIEW_DATABASES"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    MANAGE_BUCKETS = "MANAGE_BUCKETS"
    MANAGE_DATABASES = "MANAGE_DATABASES"


ROLE_TO_PERMISSIONS: dict[str, set[UserPermission]] = {
    "ws_access": {
        UserPermission.VIEW_BUCKET_CREDENTIALS,
        UserPermission.VIEW_MEMBERS,
        UserPermission.VIEW_BUCKETS,
        UserPermission.VIEW_DATABASES,
    },
    "ws_admin": {
        UserPermission.VIEW_BUCKET_CREDENTIALS,
        UserPermission.VIEW_MEMBERS,
        UserPermission.VIEW_BUCKETS,
        UserPermission.VIEW_DATABASES,
        UserPermission.MANAGE_MEMBERS,
        UserPermission.MANAGE_BUCKETS,
        # UserPermission.MANAGE_DATABASES,
    },
}


class UserContext(BaseModel):
    """User-specific context for a workspace."""

    name: str = Field(..., description="Username of the current user.")
    permissions: list[UserPermission] = Field(
        ...,
        description="Permissions of the current user within this workspace.",
    )


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


class Database(BaseModel):
    """A database belonging to a workspace with creation time."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace database entry."})

    name: str = Field(..., description="The name of the database.")
    creation_timestamp: datetime | None = Field(
        ...,
        description="When the database was created (UTC, RFC3339).",
    )

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: str) -> str:
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

    _principal: str | None = PrivateAttr(default=None)

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

    add_memberships: list[Membership] = Field(
        default_factory=list,
        description="Memberships to add.",
    )
    add_databases: list[Database] = Field(
        default_factory=list,
        description="Databases to add.",
    )
    add_buckets: list[str] = Field(default_factory=list, description="Buckets to add.")
    patch_bucket_access_requests: list[BucketAccessRequest] = Field(
        default_factory=list,
        description="Bucket access requests/grants to upsert. Each entry MUST have workspace, bucket, and request_timestamp.",
    )

    @field_validator("add_memberships")
    @classmethod
    def _dedup_memberships(cls, v: list[Membership]) -> list[Membership]:
        seen: set[str] = set()
        out: list[Membership] = []
        for m in v or []:
            if m.member in seen:
                continue
            seen.add(m.member)
            out.append(m)
        return out

    @field_validator("add_buckets")
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


class Storage(BaseModel):
    """Storage for a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace storage."})

    buckets: list[str] = Field(default_factory=list, description="Owned Buckets.")
    credentials: Credentials | None = Field(None, description="S3 credentials (bucket, keys, endpoint, region).")
    bucket_access_requests: list[BucketAccessRequest] = Field(
        default_factory=list,
        description="Bucket access requests/grants associated with the workspace.",
    )

    @field_validator("buckets")
    @classmethod
    def _bucket_lists(cls, v: list[str]) -> list[str]:
        return _validate_bucket_list(v)


class Datalab(BaseModel):
    """Datalab for a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace datalab."})

    memberships: list[Membership] = Field(default_factory=list, description="Detailed membership entries.")
    databases: list[Database] = Field(default_factory=list, description="Detailed database entries.")


class Workspace(BaseModel):
    """Workspace view model with metadata, storage, datalab, session, and registry credentials."""

    model_config = ConfigDict(json_schema_extra={"description": "Workspace resource representation."})

    name: str = Field(..., description="Unique, system-generated name.")
    creation_timestamp: datetime | None = Field(None, description="Creation timestamp of the S3 credentials secret.")
    version: str | None = Field(None, description="Resource version for optimistic locking.")
    status: WorkspaceStatus = Field(..., description="Current lifecycle status.")
    storage: Storage = Field(default_factory=Storage, description="Storage for buckets, credentials, access.")
    datalab: Datalab = Field(default_factory=Datalab, description="Datalab for memberships and sessions.")
    container_registry: ContainerRegistryCredentials | None = Field(None, description="Credentials for the workspace's container registry.")
    user: UserContext = Field(
        ...,
        description="User context with effective permissions for this workspace.",
    )

    @field_validator("creation_timestamp", mode="after")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return _coerce_utc(v)


class Endpoint(BaseModel):
    """Published endpoint of an exposed service within a workspace."""

    model_config = ConfigDict(json_schema_extra={"description": "Exposed service endpoint."})

    id: str = Field(..., description="Unique identifier.")
    url: str = Field(..., description="Public URL of the exposed service.")
