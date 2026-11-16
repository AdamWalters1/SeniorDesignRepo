// Display helpers for the side panel. A missing value always shows as a dash.

export const MISSING = '-'

export function isMissing(value) {
  return (
    value === null ||
    value === undefined ||
    value === '' ||
    (typeof value === 'number' && !Number.isFinite(value))
  )
}

// Number with a unit, or a dash when the value is missing.
export function formatValue(value, unit = '', digits = null) {
  if (isMissing(value)) return MISSING
  const text = digits === null || typeof value !== 'number' ? String(value) : value.toFixed(digits)
  if (!unit) return text
  return unit === '°' ? `${text}${unit}` : `${text} ${unit}`
}

export function formatScaled(value, divisor, unit, digits) {
  if (isMissing(value)) return MISSING
  return `${(value / divisor).toFixed(digits)} ${unit}`
}

export function formatVector(vector, unit) {
  if (!Array.isArray(vector) || vector.length !== 3 || vector.some(isMissing)) return MISSING
  return `${vector.map((v) => Number(v).toFixed(2)).join(', ')} ${unit}`
}

export function formatElementList(list) {
  if (!Array.isArray(list)) return MISSING
  return list.length === 0 ? 'none' : list.join(', ')
}

// Position flag. The pipeline sets it true when the input file gave no sensor position
// and a default was used.
export function formatPositionAssumed(value) {
  if (value === true) return 'Yes (default value)'
  if (value === false) return 'No (given in input file)'
  return MISSING
}

// The pipeline labels every detection-file point "hermespy-like", including Sionna data.
// Show that label in plain words. Any other label is shown as is.
export function formatInputType(value) {
  if (isMissing(value)) return MISSING
  return value === 'hermespy-like' ? 'Radar detections file' : String(value)
}

export function formatPolarization(value) {
  if (isMissing(value)) return MISSING
  const names = { V: 'vertical', H: 'horizontal' }
  const text = String(value)
  return names[text.toUpperCase()] ? `${text} (${names[text.toUpperCase()]})` : text
}
