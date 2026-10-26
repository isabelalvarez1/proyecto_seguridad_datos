# Dashboard web y DW de consulta

## Qué está implementado

Aplicación Vue 3, Vue Router, Vite, Tailwind CSS y Apache ECharts (licencia
Apache-2.0), conectada a FastAPI. Los gráficos no dependen de Power BI ni de
CDN. La interfaz anterior se conserva en `web/legacy/index.html` como referencia.

Páginas:

- Resumen ejecutivo: homicidios, lectura de resultados, línea, dona, matriz y contexto.
- Homicidios: detalle temporal, territorial, sexo y edad.
- Contexto: diciembre, dispersión y series en unidades separadas.
- Armas, desapariciones y defunciones: complementos con sus propias definiciones.
- Evaluación predictiva: referencias y modelos, errores por fase, observado/predicho.
- Metodología: versiones, cobertura y procedimientos.

Filtros de año/provincias compartidos y guardados en la URL; máximo cuatro
provincias para líneas comparativas. La evaluación predictiva conserva sus
propios años y controles porque es una instantánea del estudio, no un cálculo
en tiempo real del filtro global.

## Arrancar

Requisitos: Python con `requirements.txt`, Node.js compatible con Vite
(desarrollo probado con Node 24), PostgreSQL y clean/vistas preparados.

En `web/`, instalar dependencias con `npm.cmd ci` (Windows) o `npm ci`.
El uso de `npm.cmd` evita cambiar la política de ejecución de PowerShell.

Desde la raíz:

```powershell
python -m scripts.update_dashboard
python -m scripts.serve_dashboard
```

Abrir <http://127.0.0.1:8080>. API de desarrollo: <http://127.0.0.1:8000/docs>.
Ctrl+C en el lanzador detiene sus procesos. Si ya hay servicios en esos puertos,
el lanzador informa y no los termina ni crea duplicados.

Para compilar y servir todo en un proceso:

```powershell
python -m scripts.serve_dashboard --production
```

Este modo sirve la aplicación y `/api/v1` en :8080, incluyendo rutas internas
de Vue al recargar. En un despliegue público, configurar el servidor/reverse
proxy, HTTPS y acceso a PostgreSQL según el entorno real.

## Nuevo mart dimensional (dwh.web_*)

Se añadieron objetos al DW existente sin borrar el esquema histórico:

| Objeto | Responsabilidad |
|---|---|
| `web_dim_tiempo` | Año/mes; clave 0 para registros sin período, sin inventarlo. |
| `web_dim_territorio` | Provincia/cantón con claves estables y ausencias explícitas. |
| `web_fact_seguridad` | Conteos por fuente, período, territorio, sexo, grupo y categoría; cantidades/intervalos solo observados. |
| `web_fact_contexto` | Registros y numeradores/denominadores ponderados separados. |
| `web_cargas` | Metadatos, versión de fuentes, cobertura y conteos de cada carga. |
| `web_estado` | Puntero a una única carga activa. |

`scripts/refresh_dashboard.py` lee las vistas analíticas, agrupa cada fuente
por separado y comprueba sumas contra sus orígenes. Crea una nueva carga dentro
de una transacción. El puntero cambia solo cuando todos los controles pasan.
Se conservan las dos últimas cargas completas y las dimensiones mantienen sus claves.
Si una carga falla, la transacción se revierte y el informe sigue usando la anterior.

Las consultas de API usan READ ONLY/REPEATABLE READ: tarjetas, líneas, dona y
matriz proceden de una sola carga por respuesta. Los hechos y cubos históricos
sin prefijo `web_` se conservan como referencia; el frontend nuevo no los consulta.

El comando histórico `python -m scripts.run_pipeline` ahora dirige por defecto
al mart web. El cargador antiguo queda explícitamente bajo `--legacy`, no es
el flujo recomendado para el contrato nuevo de clean.

## Ingresar nuevos datos

1. Colocar archivos nuevos/revisados en la carpeta de su fuente, conservando
   el conjunto histórico que se desea analizar. Evitar archivos superpuestos
   duplicados; el sistema los señala pero no elimina registros por intuición.
2. Cargar la fuente raw, por ejemplo `python -m scripts.load_raw homicidio`.
   El lector conserva `source_file` y `source_sha256`. CSV verifica el separador
   antes de aceptar el archivo. Se construye aparte y se archiva el raw anterior
   en `raw_historial` al publicar; un fallo no sustituye la fuente con una carga parcial.
3. Ejecutar `python -m scripts.update_dashboard --from-raw`. Aplica las reglas
   vigentes, genera reportes de validación, publica clean y actualiza el mart.
4. Si la validación ya fue revisada: `python -m scripts.update_dashboard --validation-run ID`.
5. Si solo cambió clean: `python -m scripts.update_dashboard`.
6. Pulsar el botón de actualización de la página para consultar la nueva carga.

La publicación clean archiva la versión previa y **reenlaza las vistas
analíticas administradas en la misma transacción**. Sus OID se mantienen;
no quedan leyendo las tablas archivadas. Dependencias ajenas o cambios de
contrato incompatibles detienen y revierten la publicación, en vez de usar CASCADE.
`clean_preparacion` se elimina al finalizar si está vacío.

El flujo mantiene reglas verificadas, no aprende automáticamente nuevas
equivalencias de códigos ni universos. Cuando una fuente cambia estructura,
su reporte de calidad y los diccionarios deben revisarse. No se recalculan
modelos predictivos automáticamente al cargar archivos.

## API

- `/api/v1/meta`: carga, versiones, provincias, años y cobertura.
- `/api/v1/dashboard`: fuente, período, provincias, frecuencia y matriz.
- `/api/v1/context`: razones ponderadas de diciembre y cruce agregado.
- `/api/v1/evaluation`: estudio temporal completado, modelos y referencias.
- `/api/v1/map`: disponibilidad y correspondencia de cartografía opcional.

Las rutas anteriores se conservan por compatibilidad. Sus modelos legados se
cargan solo si se usan esas rutas; no impiden arrancar la aplicación actual.
Las URL de Vue usan `/api/v1` relativo al sitio; Vite lo envía a la API local.
En otro entorno se configura `web/.env` a partir de `web/.env.example` y se recompila.

## Reglas de presentación

- Cero, sin dato, período sin registro observado y error son estados distintos.
- Matriz: gris para ausencia observada, no cero; exportación mantiene NULL.
- Variación: mismos meses observados entre el último año seleccionado y el anterior.
- Dona: cantidades y porcentajes sobre todos los registros; desconocidos visibles.
- CSV: todos los territorios/categorías agregados de la selección, no solo el ranking visible.
- PNG: figura en fondo claro y resolución doble; conservar fuente, período y versión al usarla en el artículo.
- Contexto: proporciones experimentales de diciembre, no estimación provincial anual oficial.
- Evaluación: no confundir MAE/WAPE/R² con porcentaje de aciertos. Las proyecciones 2025 están etiquetadas como retrospectivas y no se genera 2026 con 2025 incompleto.
- Si cambia la versión clean, la evaluación guardada se marca desactualizada.

La matriz funciona sin cartografía. Para el mapa provincial opcional se requiere
GeoJSON verificado con los 24 códigos DPA; ver `web/public/maps/README.md`.
No se dibuja un mapa de puntos con ubicaciones imputadas.

## Verificación

```powershell
python -m unittest discover -s tests -v
$env:DASHBOARD_INTEGRATION='1'
python -m unittest tests.test_dashboard -v
```

En `web/`:

```powershell
npm.cmd test
npm.cmd run build
$env:PLAYWRIGHT_BROWSERS_PATH="$PWD\.browsers"
npm.cmd exec playwright install chromium
npm.cmd run test:e2e
```

Las pruebas de navegador requieren API y Vite activos. Comprueban filtros contra
la API real, ausencias, exportaciones, navegación y móvil. Las pruebas SQL
comprueban conservación de carga activa ante fallo, refresco repetido, razones
ponderadas y reenlace de vistas con rollback. Las capturas están en
`reports/dashboard/`, excluidas de Git.
