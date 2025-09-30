import type {WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string;
  url: string;
  creation_timestamp: string;
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

export interface Workspace {
  name: string
  version: string
  status: WorkspaceStatus
  bucket?: string
  extra_buckets?: string[]
  credentials?: Record<string, unknown>
  memberships?: Membership[]
  bucket_access_requests?: Bucket[]
}

export interface ExtraBucketUI {
  bucket: string;
  requests: number;
  grants: number;
  isNew?: boolean
  isPending?: boolean
}

export interface WorkspaceEditUI {
  name: string
  memberships: Membership[],
  extra_buckets: ExtraBucketUI[]
  linked_buckets: Bucket[]
}

// Corresponding to Backend
export interface WorkspaceEdit {
  add_members: string[]
  add_extra_buckets: string[]
  patch_bucket_access_requests?: Bucket[]
}
