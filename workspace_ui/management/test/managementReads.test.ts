import assert from 'node:assert/strict'
import test from 'node:test'
import axios from 'axios'
// @ts-expect-error Node needs the TypeScript file extension.
import { getWorkspaceForManagement, createVClusterGroup } from '../src/services/api.ts'

test('management requests declarations without resolving credentials', async (context) => {
  const workspace = { name: 'ws-alice', datalab: { vclusters: [{ name: 'vc0', groups: [] }] } }
  const request = context.mock.method(axios, 'get', async () => ({ data: workspace }))
  assert.deepEqual(await getWorkspaceForManagement('ws-alice'), workspace)
  assert.deepEqual(request.mock.calls[0]?.arguments, ['/workspaces/ws-alice', {
    params: { view: 'management', resolve_connections: 'none' },
    headers: { Accept: 'application/json' },
  }])
})

test('submits the chosen access profile name, namespace, and role', async (context) => {
  const profile = { name: 'namespace-demo', namespace: 'demo', role: 'edit' as const }
  const request = context.mock.method(axios, 'post', async () => ({ data: profile }))
  assert.deepEqual(await createVClusterGroup('ws-alice', 'vc0', profile), profile)
  assert.deepEqual(request.mock.calls[0]?.arguments, ['/workspaces/ws-alice/vclusters/vc0/groups', profile])
})
