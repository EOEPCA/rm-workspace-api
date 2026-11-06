import assert from 'node:assert/strict'
import test from 'node:test'
// @ts-expect-error Node needs the TypeScript file extension.
import { apiErrorMessage } from '../src/services/apiErrors.ts'

test('shows the field and backend validation message', () => {
  const error = {isAxiosError: true, response: {data: {detail: [
    {loc: ['body', 'name'], msg: 'Invalid resource name'},
  ]}}}
  assert.equal(apiErrorMessage(error), 'name: Invalid resource name')
})

test('shows backend request errors and network failures', () => {
  assert.equal(apiErrorMessage({isAxiosError: true, response: {data: {detail: 'Name already exists'}}}), 'Name already exists')
  assert.equal(apiErrorMessage(new Error('Network unavailable')), 'Network unavailable')
})
