import { reactive, computed, ref } from 'vue'
import router from '../router.js'
import { getJSON } from '../services/api.js'

export const state = reactive({ meta: null, start: 2018, end: 2024, provinces: [], generation: 0 })
export const metadataError = ref('')
export const metadataLoading = ref(true)
function readQuery(query) {
  if (!state.meta) return
  const start = Number(query.start ?? state.meta.defaults.start), end = Number(query.end ?? state.meta.defaults.end)
  if (state.meta.years.includes(start) && state.meta.years.includes(end) && start <= end) {
    state.start = start; state.end = end
  }
  const provinces = query.provinces ? (Array.isArray(query.provinces) ? query.provinces : [query.provinces]) : []
  state.provinces = [...new Set(provinces)].filter(p => state.meta.provinces.includes(p)).slice(0, 4)
}
export async function initialize() {
  metadataError.value = ''; metadataLoading.value = true
  try {
    state.meta = await getJSON('/meta')
    await router.isReady()
    readQuery(router.currentRoute.value.query)
    state.generation++
  } catch (e) { metadataError.value = e.message }
  finally { metadataLoading.value = false }
}
router.afterEach(to => readQuery(to.query))
export function setFilters(next) {
  Object.assign(state, next)
  const query = { start: String(state.start), end: String(state.end), provinces: state.provinces }
  router.replace({ path: router.currentRoute.value.path, query })
}
export function resetFilters() {
  setFilters({ start: state.meta.defaults.start, end: state.meta.defaults.end, provinces: [] })
}
export const parameters = computed(() => ({ start: state.start, end: state.end, provinces: state.provinces }))
export const enabled = computed(() => !!state.meta)
