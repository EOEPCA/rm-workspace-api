import type {WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string;
  url: string;
}

export interface Membership {
  id?: string;  // client-side Id
  member: string;
  role: string;
  creation_timestamp: string;
  isNew?: boolean
  isPending?: boolean
}

export interface Bucket {
  workspace: string
  bucket: string
  permission: string
  request_timestamp?: string | undefined
  grant_timestamp?: string | undefined
  denied_timestamp?: string | undefined
  isPending?: boolean
}



export interface Storage {
  buckets?: string[]
  credentials?: Record<string, unknown>
  bucket_access_requests?: Bucket[]
}

export interface Datalab {
  memberships?: Membership[]
}

export interface Workspace {
  name: string
  version: string
  status: WorkspaceStatus
  storage?: Storage
  datalab?: Datalab
}

export interface BucketUI {
  bucket: string;
  requests: number;
  grants: number;
  isNew?: boolean
  isPending?: boolean
}

export interface WorkspaceEditUI {
  name: string
  memberships: Membership[],
  buckets: BucketUI[]
  linked_buckets: Bucket[]
}

// Corresponding to Backend
export interface WorkspaceEdit {
  add_members: string[]
  add_buckets: string[]
  patch_bucket_access_requests?: Bucket[]
}
