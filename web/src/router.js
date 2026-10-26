import { createRouter, createWebHistory } from 'vue-router'

const DashboardView = () => import('./views/DashboardView.vue')
const routes = [
  { path: '/', component: DashboardView, props: { source: 'homicidios', overview: true }, meta: { title: 'Resumen ejecutivo' } },
  { path: '/homicidios', component: DashboardView, props: { source: 'homicidios' }, meta: { title: 'Homicidios' } },
  { path: '/contexto', component: () => import('./views/ContextView.vue'), meta: { title: 'Contexto socioeconómico' } },
  ...['armas', 'desapariciones', 'defunciones'].map(source => ({ path: '/' + source, component: DashboardView, props: { source }, meta: { title: source[0].toUpperCase() + source.slice(1) } })),
  { path: '/predicciones', component: () => import('./views/EvaluationView.vue'), meta: { title: 'Evaluación predictiva', ownFilters: true } },
  { path: '/metodologia', component: () => import('./views/MethodView.vue'), meta: { title: 'Fuentes y metodología', ownFilters: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]
const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })
router.afterEach(to => { document.title = `${to.meta.title} · SIS-SEG Ecuador` })
export default router
