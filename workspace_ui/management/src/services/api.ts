import type {AxiosError, AxiosResponse} from 'axios';
import axios from 'axios'
import type {Bucket, Database, WorkspaceEdit} from 'src/models/models'

export function saveMembers(workspaceName: string, members: string[], simulate = false) {
  const workspaceEdit = {
    add_members: members,
    add_buckets: [],
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  if (simulate) {
    return Promise.resolve({})
  }
  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveDatabases(workspaceName: string, databases: Database[], simulate = false) {
  console.log('TODO Save databases ', databases)
  simulate = true
  const workspaceEdit = {
    add_members: [],
    add_buckets: [],
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  if (simulate) {
    return Promise.resolve({})
  }
  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveBuckets(workspaceName: string, buckets: string[]) {
  const workspaceEdit = {
    add_members: [],
    add_buckets: buckets,
    patch_bucket_access_requests: []
  } as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveRequestedBuckets(workspaceName: string, requestedBuckets: Bucket[]) {
  const workspaceEdit = {
    add_members: [],
    add_buckets: [],
    patch_bucket_access_requests: requestedBuckets
  } as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveBucketGrants(workspaceName: string, grantedBuckets: Bucket[]) {
  const workspaceEdit = {
    add_members: [],
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
