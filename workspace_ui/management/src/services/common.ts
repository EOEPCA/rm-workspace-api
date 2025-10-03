import type {QInput, QTable} from 'quasar'
import {nextTick} from 'vue'

export function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso ?? '—'
  }
}
/*
 Scrolls to the last row in the give Quasar table
 */
export function scrollToAndFocusLastRow(tableRef: QTable | null) {
  if (!tableRef) {
    return
  }
  // Wait for DOM update, then scroll to the new row
  nextTick().then(() => {
    const tableEl = tableRef.$el as HTMLElement | undefined
    if (tableEl) {
      const rows = tableEl.querySelectorAll('tbody tr')
      const lastRow = rows[rows.length - 1] as HTMLElement | undefined
      if (!lastRow) {
        return
      }
      lastRow.scrollIntoView({behavior: 'smooth', block: 'nearest'})

      // Focus the q-input inside that row (robust selector)
      const inputEl =
        (lastRow.querySelector<HTMLInputElement>('.q-field__native input')) ||
        (lastRow.querySelector<HTMLInputElement>('input, textarea'))

      if (inputEl) {
        // Small micro-delay helps if the field is still animating
        requestAnimationFrame(() => {
          inputEl.focus()
//          inputEl.select()
          const len = inputEl.value.length
          inputEl.setSelectionRange(len, len) // move caret to end
          inputEl.focus()
        })
      }
    }
  }).catch(err => {
    console.error('nextTick failed:', err)
  })
}

export async function moveCaretToEnd(inputRef: QInput | null) {
  if (!inputRef) {
    return
  }

  await nextTick()
  // Access the native input element inside QInput
  const inputEl = inputRef.getNativeElement?.()
  if (inputEl) {
    const len = inputEl.value.length
    inputEl.setSelectionRange(len, len) // move caret to end
    inputEl.focus()
  }
}
