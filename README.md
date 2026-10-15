# SIS-SEG Ecuador

Proyecto de integración y análisis de datos de seguridad pública de Ecuador para
un artículo científico. Incluye limpieza de fuentes, almacén dimensional (DWH),
cubos OLAP, experimentos de aprendizaje automático, API y una web de consulta.

## Estado actual

- Backend: Python, FastAPI, SQLAlchemy y PostgreSQL.
- Analítica: pandas, scikit-learn y XGBoost.
- Frontend: HTML, CSS y JavaScript con indicadores desde la API y un informe
  publicado de Power BI incrustado.
- La migración a Vue/Vite/Tailwind y gráficos propios es una propuesta futura;
  aún no está implementada y no requiere Node.js para ejecutar la web actual.

## Arquitectura

```text
Archivos locales → raw → clean + catálogo DPA → dimensiones y hechos
                                              ↓
                                  cubos materializados dwh.cubo_*
                                              ↓
                            vistas dwh.v_cubo_* / API FastAPI
                                              ↓
                                 Web y análisis en Power BI
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
utils/                  Configuración, normalización, geografía y helpers
web/                    Página estática e iconos
.env.example            Plantilla de configuración sin credenciales
requirements.txt        Dependencias Python
```

## Requisitos e instalación

- Python 3.10 o superior; entorno local utilizado durante el desarrollo: Python 3.13.
- PostgreSQL accesible y permiso para crear/refrescar objetos del esquema `dwh`.
- Para reconstruir el DWH: tablas `clean` y catálogo `catalogo.dpa_ecuador` preparados.
- Para arrancar la API: artefactos de los modelos disponibles en `ml/modelos/`.

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

## Ejecutar con una base y modelos ya preparados

Abre dos terminales desde la raíz con el entorno virtual activado.

**Terminal 1 — API:**

```powershell
python -m uvicorn api.api_seguridad:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — web:**

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory web
```

- Web: <http://127.0.0.1:8080/index.html>
- API y documentación interactiva: <http://127.0.0.1:8000/docs>
- Detener cada servidor: `Ctrl+C` en su terminal.

La web usa `http://localhost:8000` para consultar la API. El iframe de Power BI
depende del informe publicado y necesita acceso a Internet; actualizar la base
local no actualiza automáticamente ese informe.

## Preparar o actualizar los datos

El repositorio no incluye las bases, archivos fuente, catálogo DPA, modelos
entrenados ni el `.pbix`. Un clon no es una instalación con datos precargados.
Consulta [data/README.md](data/README.md) para las rutas esperadas.

La carga de archivos se ejecuta por fuente, por ejemplo:

```powershell
python -m scripts.load_raw homicidio
```

Las opciones son `homicidio`, `arma`, `desaparecido`, `edg` y `enemdu`.
La limpieza utiliza `utils/pipeline.py` y los limpiadores específicos de
`scripts/clean_*.py`. Todavía no hay un comando único que reconstruya todas las
tablas `clean` y el catálogo desde una descarga nueva: deben prepararse y
documentarse antes de cargar el DWH.

### Reconstrucción inicial del esquema DWH

**Este comando elimina y recrea las tablas DWH y sus objetos dependientes.**
Úsalo para una reconstrucción deliberada, no para arrancar la página:

```powershell
python -c "from scripts.create_dwh import create_dwh; create_dwh()"
```

Con las tablas creadas y las fuentes `clean` preparadas:

```powershell
python -m scripts.run_pipeline todos
```

`todos` vacía hechos y dimensiones, reconstruye sus claves y refresca los cubos.
Puede tardar bastante: ENEMDU se procesa en chunks. No ejecutarlo a la vez que
otro proceso de carga del DWH.

| Paso | Efecto |
|---|---|
| `todos` | Vacía el DWH y carga dimensiones, hechos y cubos. |
| `dims` | Vacía hechos y dimensiones; carga solo dimensiones. Quedan pendientes hechos y cubos. |
| `facts` | Recarga los hechos usando dimensiones existentes. Queda pendiente refrescar los cubos. |
| `cubos` | Refresca los cubos y publica las vistas, sin recargar hechos. |

Para actualizar solo los resultados materializados:

```powershell
python -m scripts.run_pipeline cubos
```

### Cubos y Power BI

Existen seis cubos: `homicidio`, `arma`, `desaparicion`, `defuncion`,
`socioeconomico` y `seguridad_economia`.

- `dwh.cubo_*`: vista materializada que almacena el resultado precalculado.
- `dwh.v_cubo_*`: vista normal que lee ese resultado sin duplicar su almacenamiento.
- Para conexiones nuevas de Power BI, utilizar `dwh.v_cubo_*`.
- Refrescar los cubos no modifica automáticamente su definición SQL. La fuente
  vigente de esas definiciones es `scripts/create_cubes.py`, no `sql/archive/`.

## Entrenar los modelos que requiere la API

Ejecutar desde la raíz una vez cargados los cubos:

```powershell
python -m ml.ml_homicidio
python -c "from ml.modelo_riesgo import modelo_riesgo; modelo_riesgo()"
```

Para ejecución sin ventanas de gráficos puede establecerse antes:
`$env:MPLBACKEND='Agg'`. Los archivos resultantes y nombres esperados se describen
en [ml/modelos/README.md](ml/modelos/README.md).

La API carga los modelos al arrancar: reiniciarla después de reentrenarlos.
Los resultados experimentales actuales no constituyen una validación temporal
definitiva para el artículo; véase [docs/reproducibilidad.md](docs/reproducibilidad.md).

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
SELECT SUM(total_homicidios) FROM dwh.v_cubo_homicidio;
```

## Documentación

- [Arquitectura y mantenimiento](docs/arquitectura.md)
- [Cobertura, limitaciones y reproducibilidad científica](docs/reproducibilidad.md)
- [Datos locales y prerrequisitos](data/README.md)
- [Artefactos de modelos](ml/modelos/README.md)

## Git

Se versionan código, documentación y pruebas. Las credenciales, datos fuente,
modelos generados, entornos virtuales y archivos Power BI permanecen locales.
Los modelos se regeneran con los comandos anteriores. El push necesita un
repositorio remoto configurado; crear un commit local no lo publica en GitHub.
