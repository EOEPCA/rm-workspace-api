import type {ClusterStatus, WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string;
  url: string;
  creation_timestamp: string;
}

export interface Membership {
  member: string;
  creation_timestamp: string;
}


export interface Cluster {
  status: ClusterStatus
}

export interface Storage {
  credentials?: Record<string, unknown>;
  buckets?: string[];
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
  storage_buckets: string[]
  members: string[]
}
