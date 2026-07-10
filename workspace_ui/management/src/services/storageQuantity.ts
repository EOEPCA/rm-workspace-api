const BINARY_UNITS = ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei'] as const
const BINARY_QUANTITY_PATTERN = /^(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|Pi|Ei)?$/

export function formatStorageQuantity(quantity: string, locale?: string): string {
  const match = BINARY_QUANTITY_PATTERN.exec(quantity.trim())
  if (!match) return quantity

  const value = Number(match[1])
  const sourceUnit = match[2] ?? ''
  const sourcePower = BINARY_UNITS.indexOf(sourceUnit as (typeof BINARY_UNITS)[number])
  if (!Number.isFinite(value) || sourcePower < 0 || value === 0) return quantity

  const bytes = value * 1024 ** sourcePower
  let displayPower = 0
  for (let power = BINARY_UNITS.length - 1; power >= 1; power--) {
    if (bytes >= 1024 ** power) {
      displayPower = power
      break
    }
  }

  if (displayPower === 0) return quantity

  const displayValue = bytes / 1024 ** displayPower
  const formattedValue = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
    useGrouping: false,
  }).format(displayValue)

  return `${formattedValue}${BINARY_UNITS[displayPower]}`
}
