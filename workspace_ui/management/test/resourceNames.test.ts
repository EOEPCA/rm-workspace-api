import assert from 'node:assert/strict'
import test from 'node:test'
// @ts-expect-error Node needs the TypeScript file extension.
import { resourceNameError, workspaceNameError } from '../src/services/resourceNames.ts'

test('accepts resource names through the 30 character boundary', () => {
  for (const name of ['a', '1', 'demo-2', 'a'.repeat(30)]) assert.equal(resourceNameError(name), '')
})

test('rejects invalid resource names consistently', () => {
  for (const name of ['', 'a'.repeat(31), 'Upper', 'a.b', 'a_b', '-demo', 'demo-', 'a b']) {
    assert.notEqual(resourceNameError(name), '', name)
  }
})

test('workspace names keep the prefix outside the editable value and count it in the limit', () => {
  assert.equal(workspaceNameError('blue', 'ws-'), '')
  assert.equal(workspaceNameError('a'.repeat(27), 'ws-'), '')
  assert.match(workspaceNameError('a'.repeat(28), 'ws-'), /30 characters/)
  for (const suffix of ['', '-blue', 'Blue', 'blue-']) assert.notEqual(workspaceNameError(suffix, 'ws-'), '')
})
