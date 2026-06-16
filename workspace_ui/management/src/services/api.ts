import type {AxiosError, AxiosResponse} from 'axios'
import axios from 'axios'
import type {
  Bucket,
  BucketNew,
  Membership,
  SessionCreate,
  SessionState,
  SessionStateUpdate,
  Store,
  WorkspaceEdit,
  WorkspaceSession
} from 'src/models/models'

export function saveMembers(workspaceName: string, memberships: Membership[], simulate = false) {
  const workspaceEdit = {
    add_memberships: memberships,
    add_stores: [],
    add_buckets: [],
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  if (simulate) {
    return Promise.resolve({})
  }
  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveStores(workspaceName: string, stores: Store[], simulate = false) {
  const workspaceEdit = {
    add_memberships: [],
    add_stores: stores,
    add_buckets: [],
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  if (simulate) {
    return Promise.resolve({})
  }
  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveBuckets(workspaceName: string, buckets: BucketNew[]) {
  const workspaceEdit = {
    add_memberships: [],
    add_stores: [],
    add_buckets: buckets,
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveRequestedBuckets(workspaceName: string, requestedBuckets: Bucket[]) {
  const workspaceEdit = {
    add_memberships: [],
    add_stores: [],
    add_buckets: [],
    patch_bucket_access_requests: requestedBuckets
  } as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveBucketGrants(workspaceName: string, grantedBuckets: Bucket[]) {
  const workspaceEdit = {
    add_memberships: [],
    add_stores: [],
    add_buckets: [],
    patch_bucket_access_requests: grantedBuckets
  } as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveWorkspace(workspaceName: string, workspaceEdit: WorkspaceEdit) {
  return new Promise<object>((resolve, reject) => {
    axios
      .put(`/workspaces/${encodeURIComponent(workspaceName)}`, workspaceEdit)
      .then((response: AxiosResponse<object>) => {
        resolve(response.data)
      })
      .catch((error: AxiosError) => {
        reject(error)
      })
  })
}

export function createSession(workspaceName: string, session: SessionCreate) {
  return new Promise<WorkspaceSession>((resolve, reject) => {
    axios
      .post(`/workspaces/${encodeURIComponent(workspaceName)}/sessions`, session)
      .then((response: AxiosResponse<WorkspaceSession>) => {
        resolve(response.data)
      })
      .catch((error: AxiosError) => {
        reject(error)
      })
  })
}

export function updateSessionState(workspaceName: string, sessionName: string, state: SessionState) {
  const payload = {state} as SessionStateUpdate
  return new Promise<WorkspaceSession>((resolve, reject) => {
    axios
      .patch(`/workspaces/${encodeURIComponent(workspaceName)}/sessions/${encodeURIComponent(sessionName)}`, payload)
      .then((response: AxiosResponse<WorkspaceSession>) => {
        resolve(response.data)
      })
      .catch((error: AxiosError) => {
        reject(error)
      })
  })
}

export function deleteSession(workspaceName: string, sessionName: string) {
  return new Promise<void>((resolve, reject) => {
    axios
      .delete(`/workspaces/${encodeURIComponent(workspaceName)}/sessions/${encodeURIComponent(sessionName)}`)
      .then(() => {
        resolve()
      })
      .catch((error: AxiosError) => {
        reject(error)
      })
  })
}

export function sessionOpenUrl(workspaceName: string, sessionName: string) {
  return `/workspaces/${encodeURIComponent(workspaceName)}/sessions/${encodeURIComponent(sessionName)}`
}
