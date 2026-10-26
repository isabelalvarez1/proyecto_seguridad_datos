import { ref, watch, onBeforeUnmount, unref } from 'vue'

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
export async function getJSON(path, params = {}, signal) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue
    for (const item of Array.isArray(value) ? value : [value]) query.append(key, item)
  }
  const response = await fetch(`${base}${path}?${query}`, { signal, cache: 'no-store' })
  if (!response.ok) {
    let detail
    try { detail = (await response.json()).detail } catch { /* Respuesta no JSON. */ }
    throw new Error(typeof detail === 'string' ? detail : `La consulta no pudo completarse (${response.status}).`)
  }
  return response.json()
}
export function useResource(path, params, enabled = true) {
  const data = ref(null), error = ref(''), loading = ref(false), tick = ref(0)
  let controller
  watch(() => [unref(path), JSON.stringify(unref(params)), unref(enabled), tick.value], async () => {
    controller?.abort()
    if (!unref(enabled)) return
    const current = controller = new AbortController()
    loading.value = true; error.value = ''
    try { data.value = await getJSON(unref(path), unref(params), current.signal) }
    catch (e) { if (e.name !== 'AbortError') { error.value = e.message; data.value = null } }
    finally { if (controller === current) loading.value = false }
  }, { immediate: true })
  onBeforeUnmount(() => controller?.abort())
  return { data, error, loading, reload: () => { tick.value++ } }
}
