<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { LayoutDashboard, Activity, ChartNoAxesCombined, ShieldCheck, Users, HeartPulse, FlaskConical, BookOpen, RefreshCw, Menu, X } from '@lucide/vue'
import { state, initialize, metadataError, metadataLoading } from './stores/filters.js'
import { dateLabel } from './lib/format.js'
import FilterBar from './components/FilterBar.vue'
const route = useRoute(), mobile = ref(false)
const nav = [
  ['/', 'Resumen ejecutivo', LayoutDashboard], ['/homicidios', 'Homicidios', Activity], ['/contexto', 'Contexto socioeconómico', ChartNoAxesCombined],
  ['/armas', 'Armas e incautaciones', ShieldCheck], ['/desapariciones', 'Desapariciones', Users], ['/defunciones', 'Defunciones', HeartPulse],
  ['/predicciones', 'Evaluación predictiva', FlaskConical], ['/metodologia', 'Fuentes y metodología', BookOpen],
]
const query = computed(() => ({ start: state.start, end: state.end, provinces: state.provinces }))
onMounted(initialize)
</script>
<template>
  <button v-if="mobile" class="sidebar-backdrop" aria-label="Cerrar navegación" @click="mobile = false" />
  <aside class="sidebar" :class="{ open: mobile }">
    <RouterLink class="brand" :to="{ path: '/', query }"><span class="brand-symbol">S<span>·</span></span><span>SIS–SEG<small>ECUADOR · DATOS Y TERRITORIO</small></span></RouterLink>
    <p class="nav-heading">INFORME INTERACTIVO</p>
    <nav aria-label="Navegación principal"><template v-for="([path, label, icon], index) in nav" :key="path">
      <p v-if="index === 3" class="nav-heading mt-7">FUENTES COMPLEMENTARIAS</p><p v-if="index === 6" class="nav-heading mt-7">INVESTIGACIÓN</p>
      <RouterLink :to="{ path, query }" :class="{ active: route.path === path }" @click="mobile = false"><component :is="icon" :size="18" /><span>{{ label }}</span></RouterLink>
    </template></nav>
    <div class="sidebar-note"><span class="small-dot" /> Investigación reproducible<p>Fuentes, cobertura y límites visibles en cada resultado.</p></div>
  </aside>
  <div class="workspace">
    <header class="topbar"><div class="flex items-center gap-3"><button class="icon-button mobile-menu" aria-label="Abrir navegación" @click="mobile = !mobile"><Menu :size="22" /></button><span class="breadcrumb">Informe / <strong>{{ route.meta.title }}</strong></span></div>
      <div class="top-actions"><span v-if="state.meta" class="data-status"><span class="small-dot" /> Datos cargados</span><button class="icon-button" aria-label="Actualizar consultas" title="Volver a consultar la carga activa" @click="initialize"><RefreshCw :size="17" :class="{ spinning: metadataLoading }" /></button></div></header>
    <main class="page-shell" id="main-content">
      <section v-if="metadataError" class="panel error-panel" role="alert"><h1>No pudimos consultar los datos</h1><p>{{ metadataError }}</p><p class="muted">Comprueba la API y la carga del DW. No se muestran ceros en lugar de errores.</p><button class="button" @click="initialize">Reintentar conexión</button></section>
      <div v-else-if="!state.meta" class="loading-panel" role="status"><span class="loader" /> Preparando el informe…</div>
      <template v-else>
        <FilterBar v-if="!route.meta.ownFilters" />
        <RouterView />
        <footer class="page-footer"><span>SIS–SEG Ecuador · Registros observados, fuentes y metodología documentadas.</span><span>Carga: {{ dateLabel(state.meta.created_at) }}</span></footer>
      </template>
    </main>
  </div>
</template>
