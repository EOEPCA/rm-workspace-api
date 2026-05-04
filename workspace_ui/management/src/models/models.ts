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
  | 'MANAGE_BUCKETS'
  | 'MANAGE_MEMBERS'
  | 'MANAGE_STORES'

export type StoreType = 'database' | 'vector' | 'cache' | 'document'

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
  buckets?: BucketNew[]
  credentials?: Record<string, unknown>
  bucket_access_requests?: Bucket[]
}

export interface Datalab {
  memberships?: Membership[]
  available?: boolean
  available_store_types?: StoreType[]
  stores?: Store[]
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
  requests: number
  grants: number
  isNew?: boolean
  isPending?: boolean
}

export interface BucketNew {
  name: string
  discoverable: boolean
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
}

export interface WorkspaceEdit {
  add_memberships: Membership[]
  add_stores: Store[]
  add_buckets: BucketNew[]
  patch_bucket_access_requests?: Bucket[]
}
