import type {WorkspaceStatus} from 'src/types/workspace'

export interface Endpoint {
  id: string;
  url: string;
  creation_timestamp: string;
}

export interface Membership {
  member: string;
  creation_timestamp: string;
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

export interface WorkspaceEdit {
  name: string
  members: string[]
  extra_buckets: string[]
  linked_buckets: string[]
}
