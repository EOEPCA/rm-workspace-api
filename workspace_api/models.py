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
import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Membership(BaseModel):
    """Represents a membership between a user and a workspace."""

    member: str = Field(..., description="The username of the member.")
    creation_timestamp: datetime = Field(..., description="The creation timestamp of the membership.")


class BucketPermission(str, enum.Enum):
    """Enumeration for the types of access permissions for a bucket."""

    OWNER = "owner"
    READWRITE = "readwrite"
    READONLY = "readonly"
    NONE = "none"


class BucketAccessRequest(BaseModel):
    """Defines the request for access to a bucket."""

    workspace: str = Field(..., description="The name of the workspace requesting access to the bucket.")
    bucket: str = Field(..., description="The name of the requested bucket.")
    permission: BucketPermission = Field(..., description="The requested bucket permission.")
    request_timestamp: datetime | None = Field(
        ..., description="The timestamp when the request got issue (None if not issued yet)."
    )
    grant_timestamp: datetime | None = Field(
        ..., description="The timestamp when the request got granted (None if not granted yet)."
    )
    denied_timestamp: datetime | None = Field(
        ..., description="The timestamp when the request got denied (None if not denied yet)."
    )


class WorkspaceStatus(str, enum.Enum):
    """Enumeration for the lifecycle status of a workspace."""

    provisioning = "provisioning"
    ready = "ready"
    unknown = "unknown"


class ClusterStatus(str, enum.Enum):
    """Enumeration for the desired and actual status of a virtual cluster."""

    active = "active"
    suspended = "suspended"
    auto = "auto"


class Bucket(BaseModel):
    """Represents an S3-compatible bucket within the workspace."""

    name: str = Field(..., description="The name of the bucket.")
    permission: BucketPermission | None = Field(
        ..., description="The granted bucket permission (None if not granted yet)."
    )


class WorkspaceCreate(BaseModel):
    """Data model for creating a new workspace."""

    preferred_name: str = Field(
        "",
        description="The user-provided preferred name for the workspace. Will be slugified and (optionally) prefixed.",
    )
    default_owner: str = Field("", description="The default owner of the workspace.")


class WorkspaceEdit(BaseModel):
    """Data model for updating an existing workspace."""

    name: str = Field(..., description="The name of the workspace to edit.")
    cluster_status: ClusterStatus = Field(..., description="The desired status of the virtual cluster.")
    storage_buckets: list[str] = Field(
        ..., description="The definitive list of S3-compatible buckets for the workspace."
    )
    members: list[str] = Field(..., description="The definitive list of member usernames for the workspace.")


class StorageCredentials(BaseModel):
    """Defines the specific set of credentials for S3-compatible storage."""

    bucketname: str = Field(..., description="The name of the S3 bucket.")
    access: str = Field(..., description="The access key for the S3 storage.")
    secret: str = Field(..., description="The secret key for the S3 storage.")
    endpoint: str = Field(..., description="The S3 API endpoint URL.")
    region: str = Field(..., description="The S3 region.")


class Storage(BaseModel):
    """Represents the primary S3-compatible storage for the workspace."""

    credentials: StorageCredentials = Field(
        ..., description="A structured object containing S3 credentials (bucketname, access, secret, endpoint, region)."
    )
    buckets: list[str] = Field(
        ..., description="A list of all S3-compatible bucket names associated with the workspace."
    )


class Cluster(BaseModel):
    """Represents the virtual Kubernetes cluster associated with the workspace."""

    kubeconfig: str = Field("", description="The kubeconfig file contents for accessing the virtual cluster.")
    status: ClusterStatus = Field(..., description="The current status of the virtual cluster.")


class ContainerRegistryCredentials(BaseModel):
    """Represents credentials for the workspace's container registry."""

    username: str
    password: str

    def base64_encode_as_single_string(self) -> str:
        """Encodes the username and password as a base64 string for Docker config."""
        return base64.b64encode(f"{self.username}:{self.password}".encode()).decode()


class Workspace(BaseModel):
    """The comprehensive data model representing a single workspace and all its components."""

    name: str = Field(..., description="The unique, system-generated name of the workspace.")
    creation_timestamp: datetime | None = Field(
        None, description="The creation timestamp of the underlying Kubernetes object."
    )
    version: str | None = Field(
        None, description="The version of the underlying Kubernetes object, used for optimistic locking."
    )
    status: WorkspaceStatus = Field(..., description="The current lifecycle status of the workspace.")
    spec: Any | None = Field(
        None, description="The raw `spec` from the Kubernetes Workspace Custom Resource for debugging."
    )
    storage: Storage | None = Field(
        None, description="The primary S3-compatible storage for the workspace, including credentials and buckets."
    )
    container_registry: ContainerRegistryCredentials | None = Field(
        None, description="Credentials for the workspace's container registry."
    )
    cluster: Cluster | None = Field(None, description="Details of the virtual Kubernetes cluster.")
    members: list[str] = Field(
        default_factory=list, description="A list of usernames for all members of the workspace."
    )


class Endpoint(BaseModel):
    """Represents a network endpoint (e.g., an Ingress) exposed by the workspace."""

    id: str = Field(..., description="A unique identifier for the endpoint (e.g., the Ingress name).")
    url: str = Field(..., description="The public URL of the exposed service.")
    creation_timestamp: datetime = Field(..., description="The creation timestamp of the endpoint.")
