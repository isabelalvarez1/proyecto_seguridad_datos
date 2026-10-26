<script setup>
import { ref } from 'vue'
import { Download } from '@lucide/vue'
import ChartCanvas from './ChartCanvas.vue'
import { state } from '../stores/filters.js'
const props = defineProps({ title: String, subtitle: String, option: Object, height: { type: Number, default: 330 }, note: String, scope: String })
const emit = defineEmits(['select'])
const canvas = ref(null)
function exportFigure() {
  const scope = props.scope || `${state.start}–${state.end} · ${state.provinces.join(', ') || 'Total de la fuente'}`
  canvas.value?.exportImage([scope, `SIS–SEG Ecuador · carga ${state.meta?.batch_id || 'sin versión'}`, props.note || props.subtitle || 'Datos agregados de las fuentes integradas.'])
}
</script>
<template>
  <section class="panel chart-panel">
    <div class="panel-heading"><div><h2>{{ title }}</h2><p v-if="subtitle" class="muted text-sm">{{ subtitle }}</p></div>
      <button class="icon-button" :aria-label="'Descargar figura: ' + title" title="Descargar PNG con período y versión" @click="exportFigure"><Download :size="17" /></button></div>
    <slot name="controls" />
    <ChartCanvas ref="canvas" :option="option" :title="title" :height="height" @select="emit('select', $event)" />
    <p v-if="note" class="chart-note">{{ note }}</p>
    <slot />
  </section>
</template>
