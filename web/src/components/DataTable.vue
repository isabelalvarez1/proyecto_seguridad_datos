<script setup>
import { computed, ref } from 'vue'
import { Download } from '@lucide/vue'
import { downloadCsv, number } from '../lib/format.js'
import { state } from '../stores/filters.js'
const props = defineProps({ title: String, rows: { type: Array, default: () => [] }, columns: Array, filename: { type: String, default: 'datos' }, scope: String })
const expanded = ref(false)
const visible = computed(() => expanded.value ? props.rows : props.rows.slice(0, 12))
function exportData() {
  downloadCsv(props.rows.map(row => ({ ...row, alcance_exportacion: props.scope || `${state.start}–${state.end} · ${state.provinces.join(', ') || 'Total de la fuente'}`, carga_dw: state.meta?.batch_id })), props.filename)
}
</script>
<template>
  <section class="panel">
    <div class="panel-heading"><div><h2>{{ title }}</h2><p class="muted text-sm">{{ scope || 'Datos agregados de la selección' }} · {{ number(rows.length) }} filas</p></div>
      <button class="button secondary" :disabled="!rows.length" @click="exportData"><Download :size="15" /> CSV</button></div>
    <div class="table-scroll"><table><thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
      <tbody><tr v-for="(row, index) in visible" :key="index"><td v-for="column in columns" :key="column.key">{{ column.numeric ? number(row[column.key], column.decimals || 0) : (row[column.key] ?? 'Sin dato') }}</td></tr>
        <tr v-if="!rows.length"><td :colspan="columns.length" class="muted">No hay registros observados para esta selección.</td></tr></tbody></table></div>
    <button v-if="rows.length > 12" class="text-button mt-3" @click="expanded = !expanded">{{ expanded ? 'Mostrar menos' : 'Ver todas las filas' }}</button>
  </section>
</template>
