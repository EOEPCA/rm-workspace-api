import assert from 'node:assert/strict'
import test from 'node:test'

// @ts-expect-error Node's strip-types test runner requires the explicit TypeScript extension.
import { formatStorageQuantity, sumStorageQuantities } from '../src/services/storageQuantity.ts'

test('formats mixed binary storage totals in the largest readable unit', () => {
  assert.equal(formatStorageQuantity('46387Mi', 'en-US'), '45.3Gi')
  assert.equal(formatStorageQuantity('46387Mi', 'de-AT'), '45,3Gi')
})

test('keeps quantities below one GiB in MiB and preserves invalid values', () => {
  assert.equal(formatStorageQuantity('512Mi', 'en-US'), '512Mi')
  assert.equal(formatStorageQuantity('unavailable', 'en-US'), 'unavailable')
})

test('keeps whole storage values compact', () => {
  assert.equal(formatStorageQuantity('100Gi', 'en-US'), '100Gi')
})

test('sums persistent session storage with different units', () => {
  const total = sumStorageQuantities(['10Gi', '5120Mi'])
  assert.equal(formatStorageQuantity(total!), '15Gi')
  assert.equal(sumStorageQuantities(['0']), '0')
})

test('does not show a partial session storage total', () => {
  assert.equal(sumStorageQuantities(['10Gi', undefined]), null)
  assert.equal(sumStorageQuantities(['10Gi', 'invalid']), null)
  assert.equal(sumStorageQuantities([]), null)
})
