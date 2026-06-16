import type {WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string
  url: string
}

export type UserPermission =
  | 'VIEW_BUCKETS'
  | 'VIEW_BUCKET_CREDENTIALS'
  | 'VIEW_MEMBERS'
  | 'VIEW_STORES'
  | 'VIEW_SESSIONS'
  | 'MANAGE_BUCKETS'
  | 'MANAGE_MEMBERS'
  | 'MANAGE_STORES'
  | 'MANAGE_SESSIONS'

export type StoreType = 'database' | 'vector' | 'cache' | 'document'
export type SessionState = 'started' | 'stopped'

export type BucketLifecycleRuleMode = 'Notify' | 'Delete'

export interface WorkspaceUser {
  name: string
  permissions: UserPermission[]
}

export interface Membership {
  id?: string  // client-side Id
  member: string
  role: string
  creation_timestamp?: string | undefined
  isNew?: boolean
  isPending?: boolean
}

export interface Store {
  id: string  // client-side Id
  name: string
  type: StoreType
  storage?: string | undefined
  backup_storage?: string | undefined
  creation_timestamp?: string | undefined
  isNew?: boolean
  isPending?: boolean
}

export interface WorkspaceSession {
  id?: string
  name: string
  state: SessionState
  url?: string | undefined
  ready?: boolean
  isNew?: boolean
  isPending?: boolean
}

export interface SessionCreate {
  name: string
  state: SessionState
}

export interface SessionStateUpdate {
  state: SessionState
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

export interface BucketLifecycleRule {
  id?: string
  target: string
  mode: BucketLifecycleRuleMode
  min_age?: string | undefined
  at?: string | undefined
}

export interface Storage {
  buckets?: BucketNew[]
  credentials?: Record<string, unknown>
  bucket_access_requests?: Bucket[]
}

export interface Datalab {
  memberships?: Membership[]
  available?: boolean
  available_store_types?: StoreType[]
  stores?: Store[]
  sessions?: WorkspaceSession[]
  max_sessions?: number
  store_credentials?: Partial<Record<StoreType, Record<string, Record<string, unknown>>>>
  container_registry_credentials?: Record<string, unknown>
}

export interface Workspace {
  name: string
  version: string
  status: WorkspaceStatus
  storage?: Storage
  datalab?: Datalab
  user?: WorkspaceUser
}

export interface BucketUI {
  bucket: string;
  discoverable: boolean
  lifecycle_rules?: BucketLifecycleRule[]
  requests: number
  grants: number
  isNew?: boolean
  isPending?: boolean
}

export interface BucketNew {
  name: string
  discoverable: boolean
  lifecycle_rules?: BucketLifecycleRule[]
  creation_timestamp?: string | undefined
}

export interface WorkspaceEditUI {
  name: string
  memberships: Membership[]
  buckets: BucketUI[]
  linked_buckets: Bucket[]
  datalab_available: boolean
  available_store_types: StoreType[]
  stores: Store[]
  sessions: WorkspaceSession[]
  max_sessions: number
}

export interface WorkspaceEdit {
  add_memberships: Membership[]
  add_stores: Store[]
  add_buckets: BucketNew[]
  patch_bucket_access_requests?: Bucket[]
}
