# SIS–SEG · interfaz Vue

Desde esta carpeta:

```powershell
npm.cmd ci
npm.cmd run dev
```

Requiere FastAPI en :8000; Vite sirve :8080 y reenvía `/api`. La aplicación usa
Vue 3, Vue Router, Tailwind y ECharts con licencia Apache-2.0. No requiere Power BI.

Desde la raíz puede usarse `python -m scripts.serve_dashboard` para ambos
servicios. Documentación completa: [dashboard y actualización](../docs/dashboard_web.md).

`legacy/` conserva la página anterior. `dist/`, dependencias, navegadores y
resultados de pruebas no se versionan. El archivo lock sí se conserva.
