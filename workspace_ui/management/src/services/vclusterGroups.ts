export function namespaceError(value: string): string {
  if (!/^[a-z]([a-z0-9-]*[a-z0-9])?$/.test(value) || value.length > 63) {
    return 'Use up to 63 lowercase letters, digits, or hyphens. Start with a letter and end with a letter or digit.'
  }
  if (value === 'default' || value.startsWith('kube')) {
    return 'Use a namespace other than default or a name starting with kube.'
  }
  return ''
}

export function profileNameError(value: string, existingNames: readonly string[] = []): string {
  if (!/^[a-z]([a-z0-9-]*[a-z0-9])?$/.test(value) || value.length > 40) {
    return 'Use up to 40 lowercase letters, digits, or hyphens. Start with a letter and end with a letter or digit.'
  }
  if (value === 'cluster-admin') return 'This name is reserved.'
  if (existingNames.includes(value)) return 'An access profile with this name already exists.'
  return ''
}
