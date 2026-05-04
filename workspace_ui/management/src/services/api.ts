import type {AxiosError, AxiosResponse} from 'axios'
import axios from 'axios'
import type {Bucket, BucketNew, Membership, Store, WorkspaceEdit} from 'src/models/models'

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
