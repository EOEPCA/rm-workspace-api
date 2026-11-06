import assert from 'node:assert/strict'
import test from 'node:test'
// @ts-expect-error Node needs the TypeScript file extension.
import { namespaceError, profileNameError } from '../src/services/vclusterGroups.ts'

test('accepts workload namespaces within provider naming limits', () => {
  for (const name of ['demo', 'analysis-2', 'a'.repeat(30)]) assert.equal(namespaceError(name), '')
})

test('rejects system namespaces, kube prefixes, and invalid namespace names', () => {
  for (const name of ['', 'default', 'kube-system', 'kubefoo', '*', 'Upper', 'demo.', '-demo', 'demo-', 'a'.repeat(31)]) {
    assert.notEqual(namespaceError(name), '', name)
  }
})

test('accepts valid access profile names within provider limits', () => {
  for (const name of ['demo', 'namespace-demo', 'a'.repeat(30)]) assert.equal(profileNameError(name), '')
})

test('rejects invalid, reserved, and duplicate access profile names', () => {
  for (const name of ['', 'Upper', 'demo.', '-demo', 'demo-', 'a'.repeat(31), 'cluster-admin']) {
    assert.notEqual(profileNameError(name), '', name)
  }
  assert.notEqual(profileNameError('namespace-demo', ['namespace-demo']), '')
  assert.equal(profileNameError('namespace-demo', ['analysis']), '')
})
