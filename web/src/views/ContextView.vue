<script setup>
import { computed } from 'vue'
import { state, parameters, enabled } from '../stores/filters.js'
import { useResource } from '../services/api.js'
import { number } from '../lib/format.js'
import { scatterOption, lineOption } from '../lib/charts.js'
import KpiCard from '../components/KpiCard.vue'
import ChartPanel from '../components/ChartPanel.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DataTable from '../components/DataTable.vue'
const resource = useResource('/context', parameters, computed(() => enabled.value ? state.generation : 0))
const { data, loading, error } = resource
const contextLines = computed(() => {
  if (!data.value) return [{}, {}]
  const years = data.value.series.map(row => String(row.anio))
  return [lineOption(years, [{ name: 'Proporción ponderada experimental', data: data.value.series.map(row => row.pobreza_pct) }], '% de respuestas ponderadas'),
    lineOption(years, [{ name: 'Ingreso per cápita nominal', data: data.value.series.map(row => row.ingreso_per_capita) }], 'USD nominales')]
})
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">CRUCE TERRITORIAL EXPLORATORIO</p><h1>Contexto socioeconómico</h1><p class="page-description">Compara datos observados en diciembre sin confundir asociación, representatividad y causalidad.</p></div><span class="period-pill">{{ state.start }} — {{ state.end }}</span></div>
  <StatusBanner tone="warning"><strong>Interpretación pendiente de validación muestral.</strong> Diciembre no equivale a una ENEMDU anual provincial. No hay tasas por habitante ni efectos causales estimados.</StatusBanner>
  <div v-if="loading" class="loading-panel" role="status"><span class="loader" /> Consultando el contexto…</div>
  <StatusBanner v-else-if="error" tone="error">{{ error }} <button class="text-button" @click="resource.reload">Reintentar</button></StatusBanner>
  <template v-else-if="data">
    <div class="kpi-grid"><KpiCard label="Pares con datos para comparar" :value="number(data.paired)" detail="Provincia–año con registros de homicidio y respuestas de pobreza." /><KpiCard label="Registros de encuesta" :value="number(data.sample_records)" detail="Rondas de diciembre; no son población ni personas únicas entre años." tone="teal" /><KpiCard label="Lectura temporal" value="Diciembre" detail="Medición puntual; no representa automáticamente el promedio del año." tone="violet" /></div>
    <section class="insight-section"><div class="insight-intro"><p class="eyebrow">ANTES DE INTERPRETAR</p><h2>¿Qué permite este cruce?</h2></div><article class="insight-card"><h3>Comparar observaciones territoriales</h3><p>Cada punto combina dos fuentes agregadas por separado. Una relación entre provincias no describe a las personas que cometen o sufren violencia.</p></article><article class="insight-card"><h3>Reconocer la cobertura</h3><p>Se conservan las ausencias. Si no hay ronda de diciembre o respuestas válidas, el indicador no se completa con cero ni con otro año.</p></article></section>
    <StatusBanner v-if="!data.data.length">No hay rondas de diciembre para la selección. En los datos locales, 2025 solo tiene abril–junio y no aporta pobreza válida a este cruce.</StatusBanner>
    <template v-else>
      <ChartPanel title="Homicidios y pobreza: observaciones provincia–año" subtitle="Comparación exploratoria de conteos y proporciones; sin ajuste poblacional." :option="scatterOption(data.data)" :height="400" note="Los puntos sin ambas mediciones no se dibujan. No se presentan intervalos oficiales ENEMDU." />
      <div class="charts-two equal"><ChartPanel title="Contexto de pobreza en diciembre" subtitle="Se recombinan numeradores y denominadores, no se promedian porcentajes." :option="contextLines[0]" :height="320" /><ChartPanel title="Ingreso per cápita observado" subtitle="Valores nominales ponderados de la selección; no ajustados por inflación." :option="contextLines[1]" :height="320" /></div>
      <DataTable title="Datos agregados del cruce" :rows="data.data" :columns="[{ key: 'anio', label: 'Año' }, { key: 'provincia', label: 'Provincia' }, { key: 'homicidios', label: 'Registros homicidio', numeric: true }, { key: 'pobreza_pct', label: 'Pobreza experimental %', numeric: true, decimals: 2 }, { key: 'ingreso_per_capita', label: 'Ingreso nominal USD', numeric: true, decimals: 2 }, { key: 'pobreza_validos', label: 'Respuestas válidas', numeric: true }]" filename="contexto_exploratorio_diciembre" />
    </template>
  </template>
</template>
