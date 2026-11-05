import type {QTable} from 'quasar'
import {nextTick} from 'vue'

export function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}
export function scrollToAndFocusLastRow(tableRef: QTable | null) {
  if (!tableRef) {
    return
  }
  // Wait until Vue has added the row to the DOM.
  nextTick().then(() => {
    const tableEl = tableRef.$el as HTMLElement | undefined
    if (tableEl) {
      const rows = tableEl.querySelectorAll('tbody tr')
      const lastRow = rows[rows.length - 1] as HTMLElement | undefined
      if (!lastRow) {
        return
      }
      lastRow.scrollIntoView({behavior: 'smooth', block: 'nearest'})

      const inputEl = lastRow.querySelector<HTMLInputElement>('input, textarea')

      if (inputEl) {
        // Wait for the field animation before setting focus.
        requestAnimationFrame(() => {
          const len = inputEl.value.length
          inputEl.setSelectionRange(len, len)
          inputEl.focus()
        })
      }
    }
  }).catch(err => {
    console.error('nextTick failed:', err)
  })
}
