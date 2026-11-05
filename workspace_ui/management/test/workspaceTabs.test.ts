import assert from 'node:assert/strict'
import test from 'node:test'

// @ts-expect-error Node needs the TypeScript file extension.
import { availableManagementTabs } from '../src/services/workspaceTabs.ts'

const permissions = ['VIEW_MEMBERS', 'VIEW_BUCKETS', 'VIEW_STORES', 'VIEW_VCLUSTERS', 'VIEW_SESSIONS'] as const
const vclusters = [{ name: 'vc0', groups: [] }]

test('shows only the tabs supported by workspace resources', () => {
  assert.deepEqual(availableManagementTabs(permissions, false, true, ['database'], vclusters), ['members', 'stores', 'vclusters', 'sessions'])
  assert.deepEqual(availableManagementTabs(permissions, true, false, [], vclusters), ['buckets', 'bucketRequests'])
  assert.deepEqual(availableManagementTabs(permissions, false, false, [], []), [])
})

test('requires permissions and available store types', () => {
  assert.deepEqual(availableManagementTabs([], true, true, ['database'], vclusters), [])
  assert.deepEqual(availableManagementTabs(permissions, true, true, [], vclusters), ['members', 'buckets', 'bucketRequests', 'vclusters', 'sessions'])
})

test('hides the virtual cluster tab unless vc0 is configured', () => {
  assert.equal(availableManagementTabs(permissions, false, true, [], []).includes('vclusters'), false)
  assert.equal(availableManagementTabs(permissions, false, true, [], [{ name: 'vc1', groups: [] }]).includes('vclusters'), false)
  assert.equal(availableManagementTabs(permissions, false, true, [], vclusters).includes('vclusters'), true)
})
