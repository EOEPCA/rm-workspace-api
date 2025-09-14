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
}

export interface Bucket {
  workspace: string;
  bucket: string;
  permission: string;
  request_timestamp: string;
  grant_timestamp: string;
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
  members?: string[]
}

export interface ExtraBucketUI {
  bucket: string;
  requests: number;
  grants: number;
  isNew?: boolean
}

export interface WorkspaceEditUI {
  name: string
  memberships: Membership[],
  extra_buckets: ExtraBucketUI[]
  linked_buckets: Bucket[]
  bucketAccessRequests?: Bucket[]
}

// Corresponding to Backend
export interface WorkspaceEdit {
  name: string
  members: string[]
  extra_buckets: string[]
  linked_buckets: string[]
}
