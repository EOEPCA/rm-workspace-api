import assert from 'node:assert/strict'
import test from 'node:test'
// @ts-expect-error Node needs the TypeScript file extension.
import { resourceNameError } from '../src/services/resourceNames.ts'

test('accepts resource names through the 30 character boundary', () => {
  for (const name of ['a', '1', 'demo-2', 'a'.repeat(30)]) assert.equal(resourceNameError(name), '')
})

test('rejects invalid resource names consistently', () => {
  for (const name of ['', 'a'.repeat(31), 'Upper', 'a.b', 'a_b', '-demo', 'demo-', 'a b']) {
    assert.notEqual(resourceNameError(name), '', name)
  }
})
