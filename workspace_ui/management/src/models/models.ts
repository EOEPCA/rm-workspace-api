import type {WorkspaceStatus} from 'src/types/workspace'

export type UserPermission =
  | 'VIEW_BUCKETS'
  | 'VIEW_CONNECTION_CREDENTIALS'
  | 'VIEW_OAUTH2_CREDENTIALS'
  | 'VIEW_MEMBERS'
  | 'VIEW_RESOURCE_USAGE'
  | 'VIEW_STORES'
  | 'VIEW_SESSIONS'
  | 'VIEW_VCLUSTERS'
  | 'ISSUE_TOKENS'
  | 'MANAGE_BUCKETS'
  | 'MANAGE_MEMBERS'
  | 'MANAGE_STORES'
  | 'MANAGE_SESSIONS'
  | 'MANAGE_VCLUSTERS'

export type StoreType = 'database' | 'cache' | 'document'
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

export interface Connection {
  name: string
  type: string
  ready: boolean
  secret_ref: { name: string; namespace: string }
  endpoint?: string
  region?: string
  instance?: string
  group?: string
  target_namespace?: string
  role?: string
  credentials?: Record<string, string>
  resolution_error?: string
}

export interface OAuth2Connection extends Connection {
  issuer_url: string
}

export interface Store {
  id: string  // client-side Id
  name: string
  type: StoreType
  instance?: string
  storage?: string | undefined
  backup_storage?: string | undefined
  creation_timestamp?: string | undefined
  isNew?: boolean
  isPending?: boolean
}

export interface VClusterGroup {
  name: string
  namespace: string
  role: string
  ready?: boolean
}

export interface VCluster {
  name: string
  groups: VClusterGroup[]
}

export interface VClusterGroupCreate {
  name: string
  namespace: string
  role: 'view' | 'edit' | 'admin'
}

export interface WorkspaceSession {
  phase?: string
  message?: string
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
  available?: boolean
  buckets?: BucketNew[]
  credentials?: Record<string, unknown>
  bucket_access_requests?: Bucket[]
}

export interface PersistentVolumeClaimStorage {
  name: string
  size: string
}

export interface ResourceStorageUsage {
  quota?: string
  requested: string
  remaining?: string
  persistent_volume_claims: PersistentVolumeClaimStorage[]
}

export interface WorkspaceResourceUsage {
  storage: ResourceStorageUsage
}

export interface Datalab {
  memberships?: Membership[]
  available?: boolean
  available_store_types?: StoreType[]
  stores?: Store[]
  vclusters?: VCluster[]
  sessions?: WorkspaceSession[]
  max_sessions?: number
  connections?: Connection[]
  oauth2?: OAuth2Connection[]
}

export interface Workspace {
  name: string
  version: string
  status: WorkspaceStatus
  storage?: Storage
  datalab?: Datalab
  resource_usage?: WorkspaceResourceUsage
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
  storage_available: boolean
  datalab_available: boolean
  available_store_types: StoreType[]
  stores: Store[]
  vclusters: VCluster[]
  sessions: WorkspaceSession[]
  max_sessions: number
}

export interface WorkspaceEdit {
  add_memberships: Membership[]
  add_stores: Pick<Store, 'name' | 'type' | 'storage' | 'backup_storage'>[]
  add_buckets: BucketNew[]
  patch_bucket_access_requests?: Bucket[]
}
