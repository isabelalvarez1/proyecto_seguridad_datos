import { number, percent, months, escapeHtml } from './format.js'
export const colors = ['#2563eb', '#0d9488', '#8b5cf6', '#e58b25', '#64748b', '#db5b78']
const axis = { axisLine: { lineStyle: { color: '#dce4ee' } }, axisTick: { show: false }, axisLabel: { color: '#64748b', fontSize: 11 } }
export function lineOption(categories, series, label = 'Registros') {
  return {
    color: colors, animationDuration: 350, aria: { enabled: true },
    tooltip: { trigger: 'axis', valueFormatter: value => number(value) },
    legend: { bottom: 0, type: 'scroll', textStyle: { color: '#475569' } },
    grid: { top: 35, left: 20, right: 24, bottom: 50, containLabel: true },
    xAxis: { type: 'category', data: categories, boundaryGap: false, ...axis },
    yAxis: { type: 'value', name: label, min: 0, splitLine: { lineStyle: { color: '#edf2f7', type: 'dashed' } }, ...axis, axisLabel: { ...axis.axisLabel, formatter: v => number(v) } },
    series: series.map(item => ({ type: 'line', smooth: false, symbolSize: 6, connectNulls: false, lineStyle: { width: 3 }, emphasis: { focus: 'series' }, ...item })),
  }
}
export function timeKeys(start, end, frequency) {
  const result = []
  for (let year = start; year <= end; year++) {
    if (frequency === 'monthly') for (let month = 1; month <= 12; month++) result.push(`${year}-${String(month).padStart(2, '0')}`)
    else result.push(String(year))
  }
  return result
}
const keyOf = (row, frequency) => frequency === 'monthly' ? `${row.anio}-${String(row.mes).padStart(2, '0')}` : String(row.anio)
export function trendOption(data, selected, frequency, national) {
  const keys = timeKeys(data.filters.start, data.filters.end, frequency)
  let series
  if (!selected.length) {
    const lookup = new Map(data.national_trend.map(row => [keyOf(row, frequency), row.registros]))
    series = [{ name: 'Total de la fuente', data: keys.map(key => lookup.get(key) ?? null), areaStyle: { opacity: 0.06 } }]
  } else {
    series = selected.map(province => {
      const lookup = new Map(data.trend.filter(row => row.provincia === province).map(row => [keyOf(row, frequency), row.registros]))
      return { name: province, data: keys.map(key => lookup.get(key) ?? null) }
    })
    if (national) {
      const lookup = new Map(data.national_trend.map(row => [keyOf(row, frequency), row.registros]))
      series.push({ name: 'Total fuente · referencia', data: keys.map(key => lookup.get(key) ?? null), lineStyle: { type: 'dashed', width: 2 }, itemStyle: { color: '#94a3b8' } })
    }
  }
  const labels = keys.map(key => frequency === 'annual' && data.coverage?.some(row => String(row.anio) === key && row.meses.length < 12) ? key + '*' : key)
  return lineOption(labels, series)
}
export function donutOption(rows, name = 'sexo') {
  const total = rows.reduce((sum, row) => sum + row.registros, 0)
  const palette = { HOMBRE: '#2563eb', MUJER: '#0d9488', 'NO DETERMINADO': '#e5a52c', 'SIN DATO': '#94a3b8' }
  return {
    color: colors, aria: { enabled: true },
    tooltip: { trigger: 'item', formatter: p => `${escapeHtml(p.name)}<br><b>${number(p.value)}</b> registros · ${percent(total ? p.value / total * 100 : null)}` },
    legend: { bottom: 0, type: 'plain', selectedMode: false, textStyle: { color: '#475569', fontSize: 10 }, itemWidth: 12, itemGap: 10 },
    graphic: [{ type: 'text', left: 'center', top: '39%', style: { text: number(total), fontSize: 25, fontWeight: 700, fill: '#152b4b' } },
      { type: 'text', left: 'center', top: '49%', style: { text: 'registros', fontSize: 12, fill: '#64748b' } }],
    series: [{ type: 'pie', radius: ['48%', '67%'], center: ['50%', '44%'], avoidLabelOverlap: true,
      label: { formatter: p => `${p.name}\n${number(p.value)} · ${percent(total ? p.value / total * 100 : null)}`, fontSize: 10, color: '#475569' },
      labelLayout: { hideOverlap: true }, itemStyle: { borderColor: '#fff', borderWidth: 3 },
      data: rows.map(row => ({ name: row[name], value: row.registros, itemStyle: palette[row[name]] ? { color: palette[row[name]] } : undefined })) }],
  }
}
export function heatmapOption(data, allProvinces, frequency) {
  const selected = data.filters.provinces.length ? data.filters.provinces : allProvinces
  const totals = new Map(selected.map(p => [p, 0]))
  for (const row of data.heatmap) if (totals.has(row.provincia)) totals.set(row.provincia, totals.get(row.provincia) + row.registros)
  const provinces = [...selected].sort((a, b) => totals.get(b) - totals.get(a) || a.localeCompare(b, 'es'))
  const keys = timeKeys(data.filters.start, data.filters.end, frequency)
  const lookup = new Map(data.heatmap.map(row => [`${row.provincia}|${keyOf(row, frequency)}`, row.registros]))
  const cells = provinces.flatMap((province, y) => keys.map((key, x) => {
    const count = lookup.get(`${province}|${key}`) ?? null
    return { value: [x, y, count ?? 0], province, period: key, count,
      itemStyle: count === null ? { color: '#edf1f6', borderColor: '#fff', borderWidth: 2 } : { borderColor: '#fff', borderWidth: 2 } }
  }))
  const maximum = Math.max(1, ...cells.map(cell => cell.count ?? 0))
  return {
    aria: { enabled: true }, animationDuration: 250,
    tooltip: { formatter: p => `<b>${escapeHtml(p.data.province)}</b> · ${escapeHtml(p.data.period)}<br>${p.data.count === null ? 'Sin registro observado; no equivale a cero.' : `<b>${number(p.data.count)}</b> registros`}<br><small>Clic para explorar provincia y año</small>` },
    grid: { left: 175, right: 20, top: 15, bottom: 75 },
    xAxis: { type: 'category', data: keys.map(key => frequency === 'annual' && data.coverage?.some(row => String(row.anio) === key && row.meses.length < 12) ? key + '*' : key), splitArea: { show: false }, ...axis, axisLabel: { color: '#64748b', fontSize: 11, interval: 'auto' } },
    yAxis: { type: 'category', data: provinces, inverse: true, ...axis, axisLabel: { color: '#475569', width: 155, overflow: 'truncate', fontSize: 11 } },
    visualMap: { min: 1, max: maximum, orient: 'horizontal', left: 'center', bottom: 5, calculable: false,
      text: [number(maximum), '1 registro'], inRange: { color: ['#e0edff', '#8eb8ff', '#3d7be0', '#174799'] }, itemWidth: 15, itemHeight: 170 },
    series: [{ type: 'heatmap', data: cells, label: { show: cells.length <= 50, formatter: p => p.data.count === null ? '—' : number(p.data.count), fontSize: 11 },
      emphasis: { itemStyle: { borderColor: '#123d7e', borderWidth: 2 } } }],
  }
}
export function ageOption(rows) {
  const order = ['MENOR_DE_1_AÑO', '0-11', '12-17', '18-29', '30-44', '45-64', '65+', 'SIN DATO']
  const sorted = [...rows].sort((a, b) => order.indexOf(a.grupo_edad) - order.indexOf(b.grupo_edad))
  return { tooltip: { trigger: 'axis' }, grid: { left: 15, right: 20, top: 15, bottom: 20, containLabel: true },
    xAxis: { type: 'value', ...axis }, yAxis: { type: 'category', inverse: true, data: sorted.map(row => row.grupo_edad), ...axis },
    series: [{ type: 'bar', data: sorted.map(row => row.registros), barMaxWidth: 22, itemStyle: { color: '#4f88e5', borderRadius: [0, 5, 5, 0] } }] }
}
export function scatterOption(rows) {
  const paired = rows.filter(row => row.homicidios !== null && row.pobreza_pct !== null)
  return { color: colors, tooltip: { formatter: p => `<b>${escapeHtml(p.data.province)}</b> · ${p.data.year}<br>Pobreza experimental: ${percent(p.value[0])}<br>Registros: ${number(p.value[1])}` },
    grid: { left: 20, right: 30, top: 20, bottom: 50, containLabel: true },
    xAxis: { type: 'value', name: 'Proporción ponderada de diciembre (%)', nameLocation: 'middle', nameGap: 30, ...axis },
    yAxis: { type: 'value', name: 'Registros', ...axis, splitLine: { lineStyle: { type: 'dashed', color: '#edf2f7' } } },
    series: [{ type: 'scatter', symbolSize: 11, itemStyle: { opacity: 0.7 }, data: paired.map(row => ({ value: [row.pobreza_pct, row.homicidios], province: row.provincia ?? 'Sin provincia', year: row.anio })) }] }
}
