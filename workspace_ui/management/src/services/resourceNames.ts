export function resourceNameError(value: string): string {
  return value.length >= 1 && value.length <= 30 && /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(value)
    ? ''
    : 'Use 1-30 lowercase letters, digits, or hyphens; start and end with a letter or digit.'
}

export function workspaceNameError(value: string, prefix: string): string {
  if (!value) return prefix ? 'Enter a workspace name after the prefix.' : 'Enter a workspace name.'
  if ((prefix + value).length > 30) return 'Use up to 30 characters, including the prefix.'
  return resourceNameError(value) || resourceNameError(prefix + value)
}
