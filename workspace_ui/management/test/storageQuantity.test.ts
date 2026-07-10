import assert from 'node:assert/strict'
import test from 'node:test'

// @ts-expect-error Node's strip-types test runner requires the explicit TypeScript extension.
import { formatStorageQuantity } from '../src/services/storageQuantity.ts'

test('formats mixed binary storage totals in the largest readable unit', () => {
  assert.equal(formatStorageQuantity('46387Mi', 'en-US'), '45.3Gi')
  assert.equal(formatStorageQuantity('46387Mi', 'de-AT'), '45,3Gi')
})

test('keeps quantities below one GiB in MiB and preserves invalid values', () => {
  assert.equal(formatStorageQuantity('512Mi', 'en-US'), '512Mi')
  assert.equal(formatStorageQuantity('unavailable', 'en-US'), 'unavailable')
})

test('keeps whole quota values compact', () => {
  assert.equal(formatStorageQuantity('100Gi', 'en-US'), '100Gi')
})
