import assert from 'node:assert/strict'
import test from 'node:test'
import axios from 'axios'
import type { WorkspaceOverview } from '../src/models/models'
// @ts-expect-error Node needs the TypeScript file extension.
import { loadWorkspaceProviders, workspaceCreatePayload } from '../src/services/workspaceLifecycle.ts'

const overview: WorkspaceOverview = {
  is_admin: true, username: 'alice', workspace_name_prefix: 'ws-', workspaces: [],
  workspaces_url: '/platform/workspaces', compositions_url: '/platform/compositions', environments_url: '/platform/environments',
}

test('creation waits for all choices, preserves defaults, and submits only installed providers', async context => {
  let finishLoading!: (value: { data: string[] }) => void
  const pending = new Promise<{ data: string[] }>(resolve => { finishLoading = resolve })
  context.mock.method(axios, 'get', async (url: string, options: { params: { provider: string } }) => {
    if (url === overview.environments_url) return pending
    return { data: options.params.provider === 'storage'
      ? { available: true, compositions: ['storage-minio'] }
      : { available: false, compositions: [] } }
  })
  let loaded = false
  const loading = loadWorkspaceProviders(overview).then(result => { loaded = true; return result })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(loaded, false)
  finishLoading({ data: ['storage-minio', 'project-config'] })
  const providers = await loading
  assert.deepEqual(workspaceCreatePayload('blue', 'alice', providers), {
    preferred_name: 'blue', default_owner: 'alice', storage: { composition: 'storage-minio' },
  })
  assert.deepEqual(providers[0]!.environments['storage-minio'], ['project-config'])
  providers[0]!.environment_name = 'project-config'
  assert.deepEqual(workspaceCreatePayload('blue', 'alice', providers).storage, {
    composition: 'storage-minio', environment_name: 'project-config',
  })
})

test('unavailable choices prevent creation and allow a fresh load', async context => {
  const request = context.mock.method(axios, 'get', async () => ({ data: { available: true, compositions: [] } }))
  await assert.rejects(loadWorkspaceProviders(overview), /No storage compositions/)
  request.mock.mockImplementation(async () => { throw new Error('Configuration list unavailable') })
  await assert.rejects(loadWorkspaceProviders(overview), /Configuration list unavailable/)
  request.mock.mockImplementation(async () => ({ data: { available: false, compositions: [] } }))
  await assert.rejects(loadWorkspaceProviders(overview), /No workspace provider/)
})
