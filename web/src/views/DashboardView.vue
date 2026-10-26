<script setup>
import { computed, ref } from 'vue'
import { ArrowUpRight, Map as MapIcon, Grid3X3 } from '@lucide/vue'
import * as echarts from '../lib/echarts.js'
import { state, parameters, enabled, setFilters } from '../stores/filters.js'
import { useResource, getJSON } from '../services/api.js'
import { number, percent, months } from '../lib/format.js'
import { trendOption, donutOption, heatmapOption, ageOption, scatterOption } from '../lib/charts.js'
import ChartPanel from '../components/ChartPanel.vue'
import KpiCard from '../components/KpiCard.vue'
import StatusBanner from '../components/StatusBanner.vue'
import DataTable from '../components/DataTable.vue'
const props = defineProps({ source: { type: String, default: 'homicidios' }, overview: Boolean })
const titles = { homicidios: 'Homicidios registrados', armas: 'Armas e incautaciones', desapariciones: 'Personas desaparecidas · registros', defunciones: 'Defunciones registradas' }
const frequency = ref('annual'), heatFrequency = ref('annual'), includeNational = ref(false), heatTab = ref('matrix'), mapInfo = ref(null)
const params = computed(() => ({ ...parameters.value, source: props.source, frequency: frequency.value, heatmap: heatFrequency.value }))
const resource = useResource('/dashboard', params, computed(() => enabled.value ? state.generation : 0))
const { data, error, loading } = resource
const contextResource = useResource('/context', parameters, computed(() => enabled.value && props.overview ? state.generation : 0))
const trend = computed(() => data.value ? trendOption(data.value, state.provinces, frequency.value, includeNational.value) : {})
const heat = computed(() => data.value ? heatmapOption(data.value, state.meta.provinces, heatFrequency.value) : {})
const sex = computed(() => donutOption(data.value?.sexes || []))
const age = computed(() => ageOption(data.value?.ages || []))
const partial = computed(() => data.value?.coverage.filter(row => row.meses.length < 12) || [])
const comparisonText = computed(() => {
  const row = data.value?.comparison
  if (!row?.months.length) return 'No hay período anterior comparable.'
  return `${months[row.months[0]-1]}–${months[row.months.at(-1)-1]} ${row.year} frente a los mismos meses de ${row.previous_year}.`
})
const narrative = computed(() => {
  if (!data.value?.has_data) return []
  const d = data.value, result = []
  if (state.provinces.length) result.push({ title: 'Alcance de la selección', body: `${state.provinces.join(', ')} reúne ${percent(d.totals.selected_share_pct)} de los registros de la fuente durante el período seleccionado. Es una participación en conteos, no una tasa de riesgo.` })
  else if (d.leading) result.push({ title: 'Concentración territorial', body: `${d.leading.provincia ?? 'El territorio no informado'} reúne ${number(d.leading.registros)} registros (${percent(d.leading.registros / d.totals.registros * 100)}) de esta selección. El tamaño de población no está ajustado.` })
  const cmp = d.comparison
  result.push({ title: 'Comparación temporal', body: cmp.percent === null ? 'No existe una base comparable para calcular una variación. La ausencia no se interpreta como cero.' : `${cmp.percent >= 0 ? 'Aumento' : 'Disminución'} de ${percent(Math.abs(cmp.percent))} en registros. ${comparisonText.value}` })
  return result
})
function pickCell(event) {
  if (!event.data?.province) return
  const year = Number(event.data.period.slice(0, 4))
  setFilters({ start: year, end: year, provinces: [event.data.province] })
}
async function openMap() {
  heatTab.value = 'map'
  if (!mapInfo.value) {
    try {
      mapInfo.value = await getJSON('/map')
      if (mapInfo.value.available) echarts.registerMap('ecuador-provincial', mapInfo.value.geojson)
    } catch (e) { mapInfo.value = { available: false, note: e.message } }
  }
}
const mapOption = computed(() => {
  const totals = new Map()
  for (const row of data.value?.heatmap || []) totals.set(row.provincia, (totals.get(row.provincia) || 0) + row.registros)
  return { tooltip: { trigger: 'item', valueFormatter: v => number(v) }, visualMap: { min: 1, max: Math.max(1, ...totals.values()), inRange: { color: ['#dceaff', '#174799'] } },
    series: [{ type: 'map', map: 'ecuador-provincial', roam: true, data: [...totals].map(([name, value]) => ({ name, value })) }] }
})
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">SEGURIDAD Y CONTEXTO TERRITORIAL</p><h1>{{ overview ? 'Homicidios y contexto territorial' : titles[source] }}</h1><p class="page-description">{{ overview ? 'Un informe para entender qué cambió, dónde se concentra y cómo interpretar los datos.' : 'Explora la evolución y la composición de los registros, con cobertura y controles visibles.' }}</p></div><span class="period-pill">{{ state.start }} — {{ state.end }}</span></div>
  <div v-if="loading" class="loading-panel" role="status"><span class="loader" /> Consultando la selección…</div>
  <StatusBanner v-else-if="error" tone="error"><strong>No se pudo completar la consulta.</strong> {{ error }} <button class="text-button" @click="resource.reload">Reintentar</button></StatusBanner>
  <template v-else-if="data">
    <StatusBanner v-if="partial.length" tone="warning"><strong>Hay períodos parciales.</strong> {{ partial.map(row => `${row.anio}: ${row.meses.length} meses observados`).join(' · ') }}. La variación se calcula con los mismos meses de ambos años.</StatusBanner>
    <StatusBanner v-if="!data.has_data">No hay registros observados para esta selección. Cambia los filtros; no se presenta esta ausencia como cero.</StatusBanner>
    <template v-else>
      <div class="kpi-grid">
        <KpiCard label="Registros en la selección" :value="number(data.totals.registros)" :detail="`${state.start}–${state.end} · ${state.provinces.length ? 'provincias seleccionadas' : 'total de la fuente'}`" />
        <KpiCard v-if="source === 'armas'" label="Cantidad observada de armas" :value="number(data.totals.cantidad)" :detail="`${number(data.totals.cantidad_informada)} registros con cantidad; faltantes sin imputar.`" tone="teal" />
        <KpiCard v-else-if="source === 'desapariciones'" label="Días hasta localización" :value="number(data.totals.promedio_dias_observados, 1)" :detail="`Media solo de ${number(data.totals.duraciones_observadas)} intervalos observables; no incluye casos abiertos sin fecha.`" tone="teal" />
        <KpiCard v-else label="Territorios seleccionados" :value="state.provinces.length ? String(state.provinces.length) : '24'" detail="Provincias reconocidas para explorar. Otros territorios se conservan en los totales." tone="teal" />
        <KpiCard label="Variación en meses comparables" :value="data.comparison.percent === null ? 'No comparable' : `${data.comparison.percent > 0 ? '+' : ''}${percent(data.comparison.percent)}`" :detail="comparisonText" tone="violet" />
      </div>
      <section class="insight-section"><div class="insight-intro"><span class="eyebrow">LECTURA DE LOS DATOS</span><h2>¿Qué muestra esta selección?</h2></div><article v-for="item in narrative" :key="item.title" class="insight-card"><h3>{{ item.title }}</h3><p>{{ item.body }}</p></article></section>
      <div class="charts-two" :class="{ 'one-column': source === 'armas' }">
        <ChartPanel title="Evolución y comparación temporal" subtitle="La línea compara períodos; los espacios sin datos no se unen." :option="trend" :height="350" note="Conteos sin ajuste por población. * indica año parcial. La leyenda solo cambia la visibilidad de las series.">
          <template #controls><div class="chart-controls"><div class="segmented"><button :class="{ selected: frequency === 'annual' }" @click="frequency = 'annual'">Anual</button><button :class="{ selected: frequency === 'monthly' }" @click="frequency = 'monthly'">Mensual</button></div><label v-if="state.provinces.length" class="checkbox-label"><input v-model="includeNational" type="checkbox" /> Referencia total fuente</label></div></template>
        </ChartPanel>
        <ChartPanel v-if="source !== 'armas'" title="Composición por sexo" subtitle="Cantidad y porcentaje sobre todos los registros de la selección." :option="sex" :height="350" note="Las categorías desconocidas permanecen visibles; no se asigna el sexo por mayoría." />
      </div>
      <section class="section-heading"><div><p class="eyebrow">PATRONES EN EL TERRITORIO</p><h2>¿Dónde y cuándo se concentran los registros?</h2></div><div class="segmented"><button :class="{ selected: heatTab === 'matrix' }" @click="heatTab = 'matrix'"><Grid3X3 :size="15" /> Matriz</button><button :class="{ selected: heatTab === 'map' }" @click="openMap"><MapIcon :size="15" /> Mapa opcional</button></div></section>
      <ChartPanel v-if="heatTab === 'matrix'" title="Mapa de calor temporal" subtitle="Provincias ordenadas por registros en la selección. Haz clic en una celda para explorar." :option="heat" :height="Math.max(260, (state.provinces.length || 24) * 24 + 100)" note="Gris: sin registro observado, no equivale a cero. La matriz muestra provincias reconocidas; los totales conservan otros territorios." @select="pickCell">
        <template #controls><div class="segmented"><button :class="{ selected: heatFrequency === 'annual' }" @click="heatFrequency = 'annual'">Provincia × año</button><button :class="{ selected: heatFrequency === 'monthly' }" @click="heatFrequency = 'monthly'">Provincia × mes</button></div></template>
      </ChartPanel>
      <ChartPanel v-else-if="mapInfo?.available" title="Distribución provincial" subtitle="Conteos absolutos; no son tasas de riesgo." :option="mapOption" :height="500" />
      <section v-else class="panel map-pending"><MapIcon :size="38" /><h2>El mapa geográfico es una vista complementaria</h2><p>{{ mapInfo?.note || 'Comprobando cartografía…' }}</p><p class="muted">No se sustituyen coordenadas ausentes por ubicaciones inventadas. La matriz temporal utiliza los territorios administrativos disponibles.</p><button class="button secondary" @click="heatTab = 'matrix'">Volver a la matriz</button></section>
      <ChartPanel v-if="source !== 'armas' && !overview" title="Perfil por grupo de edad" subtitle="Agrupaciones explícitas; las edades ausentes conservan su categoría." :option="age" :height="300" note="En defunciones se distingue la edad registrada en horas, días o meses; no se interpreta como años." />
      <template v-if="overview && contextResource.data.value">
        <section class="section-heading"><div><p class="eyebrow">CONTEXTO SOCIOECONÓMICO</p><h2>Una relación para explorar, no una causa demostrada</h2></div><RouterLink class="text-button" :to="{ path: '/contexto', query: $route.query }">Explorar contexto <ArrowUpRight :size="16" /></RouterLink></section>
        <StatusBanner tone="warning">Los indicadores de diciembre son exploratorios: falta verificar el dominio provincial y el diseño ENEMDU. No se presentan como tasas provinciales anuales oficiales.</StatusBanner>
        <ChartPanel title="Homicidios y pobreza: cruce exploratorio" :subtitle="`${contextResource.data.value.paired} pares provincia–año con datos para comparar.`" :option="scatterOption(contextResource.data.value.data)" :height="350" note="Cada punto es provincia–año. Conteos sin ajuste poblacional; una asociación territorial no prueba causalidad." />
      </template>
      <StatusBanner v-if="source === 'armas'" tone="warning">Registros, eventos y cantidades no son lo mismo. Las cantidades ausentes —como en la fuente 2025— no se reemplazan por cero o uno.</StatusBanner>
      <StatusBanner v-if="source === 'desapariciones'" tone="warning">ENCONTRADO, LOCALIZADO y FALLECIDO se conservan separados. El tiempo de seguimiento de cada cohorte impide interpretar una comparación simple como tasa de resolución.</StatusBanner>
      <DataTable title="Detalle territorial de la selección" :rows="data.territories" :columns="[{ key: 'provincia', label: 'Provincia' }, { key: 'canton', label: 'Cantón' }, { key: 'registros', label: 'Registros', numeric: true }]" :filename="`${source}_${state.start}_${state.end}`" />
      <DataTable v-if="!overview" :title="source === 'desapariciones' ? 'Situación reportada' : 'Clasificación reportada'" :rows="data.categories" :columns="[{ key: 'categoria', label: 'Categoría' }, { key: 'registros', label: 'Registros', numeric: true }]" :filename="`${source}_categorias`" />
    </template>
  </template>
</template>
