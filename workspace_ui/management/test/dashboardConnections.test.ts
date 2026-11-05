import assert from 'node:assert/strict'
import test from 'node:test'
import type { Connection, Store } from '../src/models/models'
// @ts-expect-error Node needs the TypeScript file extension.
import { connectionsForStore, otherConnections } from '../src/services/dashboardConnections.ts'

const connections: Connection[] = [
  { type: 'postgres', name: 'pg0', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
  { type: 'postgres', name: 'pg1', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
  { type: 'mongo', name: 'pg0', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
  { type: 's3', name: 'primary', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
  { type: 'vcluster', name: 'admin', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
  { type: 'qdrant', name: 'legacy', ready: true, secret_ref: { name: 'test', namespace: 'workspace' } },
]
const store: Store = { id: 'analytics', name: 'analytics', type: 'database', instance: 'pg0' }

test('matches a store by service type and instance, including duplicate database names', () => {
  assert.deepEqual(connectionsForStore(store, connections), [connections[0]])
  assert.deepEqual(connectionsForStore({ ...store, instance: 'pg1' }, connections), [connections[1]])
  assert.deepEqual(connectionsForStore({ ...store, type: 'document' }, connections), [connections[2]])
  assert.deepEqual(connectionsForStore({ type: 'database' }, connections), [])
})

test('keeps unassigned connections visible when resource cards are hidden', () => {
  assert.deepEqual(otherConnections(connections, [store], true), [connections[1], connections[2]])
  assert.deepEqual(otherConnections(connections, [], false), connections.slice(0, 4))
})
