<script setup>
import { computed, ref } from 'vue'
import { state } from '../stores/filters.js'
import { useResource } from '../services/api.js'
import { number, dateLabel } from '../lib/format.js'
import { lineOption } from '../lib/charts.js'
import ChartPanel from '../components/ChartPanel.vue'
import KpiCard from '../components/KpiCard.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DataTable from '../components/DataTable.vue'
const province = ref(state.provinces[0] || 'GUAYAS'), model = ref('ultimo_anio'), phase = ref('HOLDOUT_FINAL_2024'), showForecast = ref(false)
const names = { ultimo_anio: 'Referencia · año anterior', promedio_dos_anios: 'Referencia · promedio de dos años', poisson_historial: 'Poisson · historial', poisson_contexto: 'Poisson · historial + contexto', rf_historial: 'Random Forest · historial', rf_contexto: 'Random Forest · historial + contexto' }
const resource = useResource('/evaluation', computed(() => ({ province: province.value })), computed(() => state.meta ? state.generation : 0))
const { data, error, loading } = resource
const metricRows = computed(() => (data.value?.metrics || []).filter(row => row.phase === phase.value).map(row => ({ ...row, model_label: names[row.model] })).sort((a, b) => a.mae - b.mae))
const errorChart = computed(() => ({ tooltip: { trigger: 'axis', valueFormatter: v => number(v, 2) }, grid: { left: 20, right: 25, top: 15, bottom: 20, containLabel: true },
  xAxis: { type: 'value', name: 'MAE', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: '#edf2f7' } } },
  yAxis: { type: 'category', inverse: true, data: metricRows.value.map(row => row.model_label), axisLabel: { color: '#475569', fontSize: 11 } },
  series: [{ type: 'bar', barMaxWidth: 26, data: metricRows.value.map(row => ({ value: row.mae, itemStyle: { color: row.model.startsWith('ultimo') || row.model.startsWith('promedio') ? '#0d9488' : '#5489dd' } })) }] }))
const predictedRows = computed(() => (data.value?.predictions || []).filter(row => row.model === model.value).sort((a, b) => a.anio - b.anio))
const predictedChart = computed(() => lineOption(predictedRows.value.map(row => String(row.anio)), [
  { name: 'Observado', data: predictedRows.value.map(row => row.actual) }, { name: names[model.value], data: predictedRows.value.map(row => row.predicted), lineStyle: { type: 'dashed', width: 3 } },
]))
const best = computed(() => metricRows.value[0])
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">COMPROBAR ANTES DE PROYECTAR</p><h1>Evaluación predictiva</h1><p class="page-description">¿Añadir contexto mejora el pronóstico frente a una referencia sencilla? Aquí se muestran los errores, no solo las predicciones.</p></div><span class="period-pill">Estudio retrospectivo</span></div>
  <StatusBanner tone="warning"><strong>Experimento, no modelo operativo aprobado.</strong> El contexto de diciembre requiere validar su representatividad provincial y las fechas históricas de publicación.</StatusBanner>
  <div v-if="loading" class="loading-panel" role="status"><span class="loader" /> Leyendo la evaluación guardada…</div>
  <StatusBanner v-else-if="error" tone="error">{{ error }}</StatusBanner>
  <StatusBanner v-else-if="data && !data.available">{{ data.note }}</StatusBanner>
  <template v-else-if="data?.available">
    <StatusBanner v-if="data.outdated" tone="warning">La versión del DW cambió desde este estudio. Los resultados se conservan como evidencia histórica; debe repetirse la evaluación antes de una nueva proyección.</StatusBanner>
    <div class="kpi-grid"><KpiCard label="Predicciones fuera de tiempo" :value="number(data.results.out_of_sample_province_years)" detail="Observaciones provincia–año de 2022, 2023 y 2024 por método." /><KpiCard label="Menor error en la fase" :value="best ? number(best.mae, 2) : 'Sin dato'" :detail="best ? `${names[best.model]} · MAE en registros.` : ''" tone="teal" /><KpiCard label="Estado del resultado" value="Experimental" :detail="`Estudio: ${dateLabel(data.created_at)}. No es una tasa de riesgo.`" tone="violet" /></div>
    <section class="insight-section"><div class="insight-intro"><p class="eyebrow">CONCLUSIÓN DEL EXPERIMENTO</p><h2>La referencia también importa</h2></div><article class="insight-card"><h3>Más complejidad no garantizó menor error</h3><p>En el estudio guardado, las referencias sencillas superaron a los modelos ensayados. Añadir pobreza e ingreso no mostró una mejora consistente.</p></article><article class="insight-card"><h3>Evaluación por tiempo</h3><p>Se entrena con años anteriores y se evalúa en el siguiente. El contexto se rezagó dos años; no se utilizó el resultado del año a predecir como entrada.</p></article></section>
    <ChartPanel title="Comparación de errores" subtitle="Cohorte global de 23 provincias; no solo la provincia del gráfico inferior. Menor MAE es mejor." :scope="`${phase} · cohorte global · estudio ${data.run_id}`" :option="errorChart" :height="330" note="No es porcentaje de aciertos. La métrica global puede estar influida por provincias grandes.">
      <template #controls><label class="inline-control">Fase<select v-model="phase" aria-label="Fase de evaluación"><option value="HOLDOUT_FINAL_2024">2024 · evaluación final</option><option value="ALL_TEMPORAL">Conjunto 2022–2024</option><option value="DEVELOPMENT_2022_2023">2022–2023 · desarrollo</option></select></label></template>
    </ChartPanel>
    <ChartPanel title="Observado frente a predicho" :subtitle="province + ' · mismos años y provincia para comparar.'" :scope="`2022–2024 · ${province} · estudio ${data.run_id}`" :option="predictedChart" :height="350" note="Una línea cercana en una provincia no sustituye la evaluación de todo el conjunto.">
      <template #controls><div class="form-row"><label>Provincia<select v-model="province" aria-label="Provincia evaluada"><option v-for="p in state.meta.provinces" :key="p" :value="p">{{ p }}</option></select></label><label>Método<select v-model="model" aria-label="Método predictivo"><option v-for="(label, key) in names" :key="key" :value="key">{{ label }}</option></select></label></div></template>
      <StatusBanner v-if="!predictedRows.length">Esta provincia no pertenece al conjunto evaluado con historial y contexto completos. No se inventa una predicción para reemplazarla.</StatusBanner>
    </ChartPanel>
    <DataTable title="Métricas de la fase seleccionada" :scope="`${phase} · cohorte global · estudio ${data.run_id}`" :rows="metricRows" :columns="[{ key: 'model_label', label: 'Método' }, { key: 'n', label: 'Observaciones', numeric: true }, { key: 'mae', label: 'MAE', numeric: true, decimals: 2 }, { key: 'rmse', label: 'RMSE', numeric: true, decimals: 2 }, { key: 'wape_pct', label: 'WAPE %', numeric: true, decimals: 2 }]" filename="evaluacion_temporal" />
    <section class="panel"><h2>Proyecciones retrospectivas de referencia</h2><p class="muted mt-2">El archivo contiene un ejercicio de 2025. No representa una predicción nueva de 2026; 2025 no está completo en la fuente local.</p><label class="checkbox-label mt-4"><input v-model="showForecast" type="checkbox" :disabled="data.outdated" /> Entiendo el alcance y quiero ver el ejercicio retrospectivo de referencia</label></section>
    <DataTable v-if="showForecast && !data.outdated" title="Ejercicio 2025 · no validado como año completo" :scope="`Retrospectivo 2025 · ${province} · estudio ${data.run_id}`" :rows="data.forecast.map(row => ({ ...row, method: names[row.model] }))" :columns="[{ key: 'provincia', label: 'Provincia' }, { key: 'anio', label: 'Año' }, { key: 'method', label: 'Referencia' }, { key: 'predicted', label: 'Proyección experimental', numeric: true, decimals: 1 }]" filename="proyeccion_retrospectiva_no_operativa" />
  </template>
</template>
