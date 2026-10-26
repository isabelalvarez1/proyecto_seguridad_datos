# SIS-SEG Ecuador

Proyecto de integración y análisis de datos de seguridad pública de Ecuador para
un artículo científico. Incluye limpieza de fuentes, almacén dimensional (DWH),
cubos OLAP, experimentos de aprendizaje automático, API y una web de consulta.

## Estado actual

- Backend: Python, FastAPI, SQLAlchemy y PostgreSQL.
- Analítica: pandas, scikit-learn y XGBoost.
- Frontend: Vue 3, Vue Router, Vite, Tailwind y Apache ECharts, con diseño claro,
  filtros compartidos, líneas, matriz de calor, donas y exportaciones.
- DW de consulta versionado (`dwh.web_*`) con publicación atómica de cargas.
- La aplicación actual no utiliza Power BI; la página anterior está archivada
  en `web/legacy/`. El estudio predictivo se muestra separado del dato observado.

## Arquitectura

```text
Archivos → raw → validación → clean + catálogo DPA
                                ↓
                     vistas normales analitica.*
                                ↓
                    mart dimensional dwh.web_*
                                ↓
                     FastAPI /api/v1 → Vue

Estudios temporales → reports/investigacion → evaluación en la web
```

## Estructura

```text
api/                    API HTTP y endpoints de predicción
data/                   Datos locales excluidos de Git; instrucciones en su README
docs/                   Arquitectura y criterios de reproducibilidad
logs/                   Registros locales e históricos de las cargas
ml/                     Exploración y entrenamiento
  modelos/              Modelos y figuras generados (no se versionan)
scripts/                Carga, limpieza y orquestación del DWH
  diagnostics/          Comprobaciones manuales de solo lectura
sql/
  archive/              SQL histórico; no es el mecanismo vigente de despliegue
tests/                  Pruebas de regresión sin conexión a la base
analysis/               EDA y limpieza aislada en clean_validacion
reports/                Resultados locales del análisis (excluidos de Git)
utils/                  Configuración, normalización, geografía y helpers
web/                    Aplicación Vue, pruebas, configuración Vite y página anterior
.env.example            Plantilla de configuración sin credenciales
requirements.txt        Dependencias Python
```

## Requisitos e instalación

- Python 3.10 o superior; entorno local utilizado durante el desarrollo: Python 3.13.
- Node.js compatible con Vite; probado con Node 24. Usar `npm.cmd` en PowerShell.
- PostgreSQL accesible y permiso para crear/refrescar objetos del esquema `dwh`.
- Para reconstruir el DWH: tablas `clean` y catálogo `catalogo.dpa_ecuador` preparados.
- La API actual arranca sin los modelos legados. La evaluación utiliza reportes
  completados; las rutas predictivas antiguas cargan sus modelos solo al usarlas.

Desde la raíz del proyecto, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Si ya existe `.env`, edítalo en lugar de sobrescribirlo. Completa `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER` y `DB_PASSWORD` con tu conexión PostgreSQL.
`utils/config.py` carga ese archivo; las variables del entorno tienen prioridad.
El archivo real `.env` está excluido de Git.

## Ejecutar con clean preparado

En `web/`, instalar dependencias: `npm.cmd ci`. Después, desde la raíz:

```powershell
python -m scripts.update_dashboard
python -m scripts.serve_dashboard
```

- Web: <http://127.0.0.1:8080>
- API de desarrollo: <http://127.0.0.1:8000/docs>
- `Ctrl+C` detiene los procesos creados por el lanzador.
- Producción local (compila y sirve web+API): `python -m scripts.serve_dashboard --production`.

La aplicación consulta `/api/v1` relativo al sitio. La configuración y los
contratos están en [dashboard web y actualización](docs/dashboard_web.md).

## Preparar o actualizar los datos

El repositorio no incluye las bases, archivos fuente, catálogo DPA, modelos
entrenados ni el `.pbix`. Un clon no es una instalación con datos precargados.
Consulta [data/README.md](data/README.md) para las rutas esperadas.

La carga de archivos se ejecuta por fuente, por ejemplo:

```powershell
python -m scripts.load_raw homicidio
```

Las opciones son `homicidio`, `arma`, `desaparecido`, `edg` y `enemdu`.
El catálogo DPA se prepara por separado. El flujo de limpieza aprobado utiliza
una validación revisada y un comando independiente del DW:

```powershell
python -m analysis.run_clean_validation
python -m scripts.run_clean --validation-run IDENTIFICADOR_REVISADO --plan
python -m scripts.run_clean --validation-run IDENTIFICADOR_REVISADO --publish
```

`run_clean` construye primero en `clean_preparacion`, verifica y publica las
cinco tablas de `clean` juntas. Conserva las tablas previas; no recarga el DW
ni los cubos. Ver [publicación de clean](docs/publicacion_clean.md) para los
contratos y tratamientos. Los limpiadores antiguos se mantienen por compatibilidad;
no sustituyen este flujo de validación y publicación.

### Actualizar el DW y la web con nuevas fuentes

```powershell
python -m scripts.update_dashboard --from-raw
```

El comando valida raw actual, publica clean conservando sus versiones, reenlaza
las vistas administradas y actualiza `dwh.web_*`. Si clean ya está actualizado,
usar `python -m scripts.update_dashboard` para refrescar solo el mart.

El mart conserva dos cargas completas y cambia el puntero activo al terminar.
Una actualización fallida conserva la última carga. Los comandos de arranque
no reconstruyen datos ni reentrenan modelos automáticamente.

### Compatibilidad histórica

Las tablas, materializadas y vistas `dwh.cubo_*`/`dwh.v_cubo_*` anteriores se
conservan, pero la web nueva utiliza `dwh.web_*`. `scripts/create_dwh.py` y el
cargador `run_pipeline --legacy` pertenecen al flujo anterior; no son necesarios
para inicializar el mart web. `run_pipeline` sin `--legacy` dirige al mart actual.

## Evaluación predictiva

```powershell
python -m analysis.run_provincial_study
```

El estudio exporta resultados temporales y modelos experimentales a una carpeta
versionada de `reports/investigacion/`. La web muestra una evaluación completada
y marca si su versión de datos difiere del DW actual. `RESEARCH_RUN_ID` permite
fijar el estudio mostrado. No se promocionan modelos experimentales a producción.
Los modelos históricos en `ml/modelos/` se mantienen para rutas legadas.

## Verificación

Pruebas de regresión sin conexión a PostgreSQL:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q api scripts utils ml tests
```

Comprobación manual con catálogo DPA disponible (solo lectura):

```powershell
python -m scripts.diagnostics.check_geo
```

Diagnóstico ampliado, que requiere tablas `clean` y cubos cargados:

```powershell
python -m scripts.diagnostics.diagnose_provincias
```

Para revisar el total de homicidios sin confundir filas agregadas con casos:

```sql
SELECT SUM(registros) FROM dwh.web_fact_seguridad
WHERE fuente='homicidios'
  AND batch_id=(SELECT active_batch_id FROM dwh.web_estado WHERE singleton=1);
```

## Documentación

- [Entrega y verificación del dashboard](docs/entrega_dashboard.md)
- [Dashboard Vue, DW y actualización con nuevos datos](docs/dashboard_web.md)
- [Protocolo provincial y evaluación predictiva temporal](docs/protocolo_provincia_anio.md)
- [Resultados y conclusiones del experimento provincial](docs/resultados_estudio_provincial.md)
- [Vistas normales, selección de variables y tratamiento de faltantes](docs/vistas_analiticas.md)
- [Resultados de la selección analítica](docs/resultados_seleccion_analitica.md)
- [Construcción y publicación de clean](docs/publicacion_clean.md)
- [Resultados del nuevo clean publicado](docs/resultados_clean_20261018.md)
- [EDA y limpieza de prueba sin actualizar el DW](docs/validacion_clean.md)
- [Arquitectura y mantenimiento](docs/arquitectura.md)
- [Cobertura, limitaciones y reproducibilidad científica](docs/reproducibilidad.md)
- [Datos locales y prerrequisitos](data/README.md)
- [Artefactos de modelos](ml/modelos/README.md)

## Git

Se versionan código, documentación y pruebas. Las credenciales, datos fuente,
modelos generados, entornos virtuales y archivos Power BI permanecen locales.
Los modelos se regeneran con los comandos anteriores. El push necesita un
repositorio remoto configurado; crear un commit local no lo publica en GitHub.
