import axios from 'axios'
import type { VClusterGroup, VClusterGroupCreate } from 'src/models/models'
import type { Bucket, BucketNew, Membership, SessionCreate, SessionState, Store, Workspace, WorkspaceEdit, WorkspaceSession } from 'src/models/models'

export function saveMembers(workspaceName: string, memberships: Membership[]) {
  return saveWorkspace(workspaceName, { add_memberships: memberships })
}

export function saveStores(workspaceName: string, stores: Store[]) {
  return saveWorkspace(workspaceName, {
    add_stores: stores.map(({ name, type, storage, backup_storage }) => ({ name, type, storage, backup_storage })),
  })
}

export function saveBuckets(workspaceName: string, buckets: BucketNew[]) {
  return saveWorkspace(workspaceName, { add_buckets: buckets })
}

export function saveBucketAccessRequests(workspaceName: string, requests: Bucket[]) {
  return saveWorkspace(workspaceName, { patch_bucket_access_requests: requests })
}

async function saveWorkspace(workspaceName: string, update: Partial<WorkspaceEdit>) {
  const response = await axios.put<{ name: string }>(`/workspaces/${encodeURIComponent(workspaceName)}`, update)
  return response.data
}

export async function createSession(workspaceName: string, session: SessionCreate) {
  const response = await axios.post<WorkspaceSession>(`/workspaces/${encodeURIComponent(workspaceName)}/sessions`, session)
  return response.data
}

export async function updateSessionState(workspaceName: string, sessionName: string, state: SessionState) {
  const response = await axios.patch<WorkspaceSession>(
    `/workspaces/${encodeURIComponent(workspaceName)}/sessions/${encodeURIComponent(sessionName)}`,
    { state },
  )
  return response.data
}

export async function deleteSession(workspaceName: string, sessionName: string): Promise<void> {
  await axios.delete(`/workspaces/${encodeURIComponent(workspaceName)}/sessions/${encodeURIComponent(sessionName)}`)
}

export async function createVClusterGroup(workspaceName: string, instance: string, group: VClusterGroupCreate): Promise<VClusterGroup> {
  const response = await axios.post<VClusterGroup>(
    `/workspaces/${encodeURIComponent(workspaceName)}/vclusters/${encodeURIComponent(instance)}/groups`, group,
  )
  return response.data
}

export async function getWorkspaceForManagement(workspaceName: string): Promise<Workspace> {
  const response = await axios.get<Workspace>(`/workspaces/${encodeURIComponent(workspaceName)}`, {
    params: { view: 'management', resolve_connections: 'none' },
    headers: { Accept: 'application/json' },
  })
  return response.data
}
