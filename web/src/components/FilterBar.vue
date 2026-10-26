<script setup>
import { computed } from 'vue'
import { RotateCcw, X, SlidersHorizontal } from '@lucide/vue'
import { state, setFilters, resetFilters } from '../stores/filters.js'
const years = computed(() => state.meta?.years || [])
function setStart(event) { const start = Number(event.target.value); setFilters({ start, end: Math.max(start, state.end) }) }
function addProvince(event) {
  if (event.target.value && !state.provinces.includes(event.target.value)) setFilters({ provinces: [...state.provinces, event.target.value] })
  event.target.value = ''
}
</script>
<template>
  <section class="filter-bar" aria-label="Filtros compartidos">
    <div class="filter-intro"><SlidersHorizontal :size="17" /><span>Explorar datos</span></div>
    <label>Desde<select aria-label="Año inicial" :value="state.start" @change="setStart"><option v-for="year in years" :key="year" :value="year">{{ year }}</option></select></label>
    <label>Hasta<select aria-label="Año final" :value="state.end" @change="setFilters({ end: Number($event.target.value) })"><option v-for="year in years.filter(y => y >= state.start)" :key="year" :value="year">{{ year }}</option></select></label>
    <label class="province-filter">Comparar provincias <span class="muted font-normal">(máx. 4)</span>
      <select aria-label="Añadir provincia" :disabled="state.provinces.length >= 4" @change="addProvince"><option value="">{{ state.provinces.length ? 'Añadir provincia…' : 'Todo el país · seleccionar provincia' }}</option><option v-for="province in state.meta.provinces.filter(p => !state.provinces.includes(p))" :key="province" :value="province">{{ province }}</option></select></label>
    <button class="button secondary reset-filter" @click="resetFilters"><RotateCcw :size="15" /> Restablecer</button>
    <div v-if="state.provinces.length" class="province-chips"><button v-for="province in state.provinces" :key="province" class="chip" :aria-label="'Quitar ' + province" @click="setFilters({ provinces: state.provinces.filter(p => p !== province) })">{{ province }} <X :size="13" /></button><button class="text-button" @click="setFilters({ provinces: [] })">Todo el país</button></div>
  </section>
</template>
