// @ts-expect-error Node tests need the TypeScript file extension.
import { resourceNameError } from './resourceNames.ts'

export function namespaceError(value: string): string {
  const error = resourceNameError(value)
  if (error) return error
  if (value === 'default' || value.startsWith('kube')) {
    return 'Use a namespace other than default or a name starting with kube.'
  }
  return ''
}

export function profileNameError(value: string, existingNames: readonly string[] = []): string {
  const error = resourceNameError(value)
  if (error) return error
  if (value === 'cluster-admin') return 'This name is reserved.'
  if (existingNames.includes(value)) return 'An access profile with this name already exists.'
  return ''
}
