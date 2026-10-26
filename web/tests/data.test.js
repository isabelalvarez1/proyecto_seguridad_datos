import test from 'node:test'
import assert from 'node:assert/strict'
import { number, percent, csvText, escapeHtml } from '../src/lib/format.js'
import { timeKeys, heatmapOption, trendOption, donutOption } from '../src/lib/charts.js'

test('zero, missing and tiny proportions remain distinguishable', () => {
  assert.equal(number(0), '0')
  assert.equal(number(null), 'Sin dato')
  assert.equal(number(undefined), 'Sin dato')
  assert.equal(percent(0.002), '<0,1 %')
  assert.equal(percent(null), 'No comparable')
})
test('CSV keeps missing values blank and quotes potential formulas', () => {
  const text = csvText([{ campo: '=SUM(A1)', valor: null, cero: 0 }])
  assert.ok(text.includes("'=SUM(A1)"))
  assert.ok(text.includes(',"","0"'))
  assert.equal(escapeHtml('<script>'), '&lt;script&gt;')
})
test('time axes include missing months without inventing records', () => {
  assert.equal(timeKeys(2025, 2025, 'monthly').length, 12)
  const data = { filters: { start: 2025, end: 2025 }, trend: [], national_trend: [{ anio: 2025, mes: 1, registros: 5 }] }
  const option = trendOption(data, [], 'monthly', false)
  assert.equal(option.series[0].data[0], 5)
  assert.equal(option.series[0].data[11], null)
  assert.equal(option.series[0].connectNulls, false)
  data.coverage = [{ anio: 2025, meses: [1, 2] }]
  assert.equal(trendOption(data, [], 'annual', false).xAxis.data[0], '2025*')
})
test('heatmap missing cells export null and explain the gap', () => {
  const option = heatmapOption({ filters: { start: 2024, end: 2024, provinces: [] }, heatmap: [] }, ['GUAYAS'], 'annual')
  const cell = option.series[0].data[0]
  assert.equal(cell.count, null)
  assert.ok(option.tooltip.formatter({ data: cell }).includes('no equivale a cero'))
})
test('sex composition uses all records and does not hide unknowns', () => {
  const option = donutOption([{ sexo: 'HOMBRE', registros: 100 }, { sexo: 'SIN DATO', registros: 1 }])
  assert.equal(option.series[0].data.length, 2)
  assert.equal(option.legend.selectedMode, false)
})
