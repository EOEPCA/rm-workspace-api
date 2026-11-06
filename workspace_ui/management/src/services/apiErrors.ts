import axios from 'axios'

export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((item: {loc?: (string | number)[]; msg?: string}) =>
        `${item.loc?.slice(1).join('.') ?? 'Request'}: ${item.msg ?? 'Invalid value'}`,
      ).join('; ')
    }
    if (detail && typeof detail === 'object') {
      const value = detail as {message?: string; error?: string}
      if (typeof value.message === 'string') return value.message
      if (typeof value.error === 'string') return value.error
    }
  }
  return error instanceof Error ? error.message : String(error)
}
