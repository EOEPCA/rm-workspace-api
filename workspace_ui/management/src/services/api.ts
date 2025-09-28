import type {AxiosError, AxiosResponse} from 'axios';
import axios from 'axios'
import type {Bucket, WorkspaceEdit} from 'src/models/models'

export function saveMembers(workspaceName: string, members: string[]) {
  const workspaceEdit = {
    name: workspaceName,
    members: members
  } as unknown as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveExtraBuckets(workspaceName: string, extraBuckets: string[]) {
  const workspaceEdit = {
    name: workspaceName,
    members: [],
    extra_buckets: extraBuckets
  } as unknown as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveRequestedBuckets(workspaceName: string, requestedBuckets: string[]) {
  const workspaceEdit = {
    name: workspaceName,
    members: [],
    linked_buckets: requestedBuckets
  } as unknown as WorkspaceEdit

  return saveWorkspace(workspaceName, workspaceEdit)
}

export function saveBucketGrants(workspaceName: string, grantedBuckets: Bucket[]) {
  const workspaceEdit = {
    name: workspaceName,
    members: [],
    bucket_access_requests: grantedBuckets
  } as unknown as WorkspaceEdit

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
