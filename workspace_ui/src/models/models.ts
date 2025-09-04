import type {ClusterStatus, WorkspaceStatus} from 'src/types/workspace'

export interface Member {
  name: string
}

export interface Bucket {
  name: string
  policy?: string
}

export interface Cluster {
  status: ClusterStatus
}

export interface StorageInfo {
  credentials?: Record<string, unknown>
}

export interface Workspace {
  name: string
  status: WorkspaceStatus
  storage?: StorageInfo
  cluster?: Cluster
//  clusterStatus?: ClusterStatus
  members?: Member[]
  buckets?: Bucket[]
}

export interface WorkspaceEdit {
  name: string
  members: string[]
  clusterStatus: ClusterStatus
  extraBuckets: string[]
}
