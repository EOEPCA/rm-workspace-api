export function resourceNameError(value: string): string {
  return value.length >= 1 && value.length <= 30 && /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(value)
    ? ''
    : 'Use 1-30 lowercase letters, digits, or hyphens; start and end with a letter or digit.'
}
