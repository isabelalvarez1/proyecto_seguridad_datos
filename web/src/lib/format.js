export function number(value, decimals = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Sin dato'
  return new Intl.NumberFormat('es-EC', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Number(value))
}
export function percent(value, decimals = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'No comparable'
  if (value > 0 && value < 0.1) return '<0,1 %'
  return number(value, decimals) + ' %'
}
export const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
export function dateLabel(value) {
  return value ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Sin fecha'
}
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}
export function csvText(rows) {
  if (!rows.length) return '\uFEFF'
  const keys = Object.keys(rows[0])
  const cell = value => {
    let text = value === null || value === undefined ? '' : String(value)
    if (typeof value === 'string' && /^[=+@-]/.test(text)) text = "'" + text
    return '"' + text.replaceAll('"', '""') + '"'
  }
  return '\uFEFF' + [keys.map(cell).join(','), ...rows.map(row => keys.map(key => cell(row[key])).join(','))].join('\r\n')
}
export function downloadCsv(rows, name) {
  const url = URL.createObjectURL(new Blob([csvText(rows)], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a'); link.href = url; link.download = name + '.csv'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
