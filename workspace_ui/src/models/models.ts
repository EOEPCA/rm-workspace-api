import type {ClusterStatus, WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string;
  url: string;
  timestamp: string;
}

export interface Membership {
  member: string;
  timestamp: string;
}

export interface Grant {
  bucket: string;
  permission: string;
  timestamp: string;
}

export interface Bucket {
  name: string
  permission?: string
}

export interface Cluster {
  status: ClusterStatus
  buckets: Bucket[]
}

export interface Storage {
  credentials?: Record<string, unknown>;
  buckets?: Bucket[];
}

export interface Workspace {
  name: string
  version: string
  status: WorkspaceStatus
  storage?: Storage
  cluster?: Cluster
  members?: string[]
}

export interface WorkspaceEdit {
  name: string
  cluster_status: ClusterStatus
  storage_buckets: Bucket[]
  members: string[]
}
