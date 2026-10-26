# Resultados de la limpieza de prueba — 16 de octubre de 2026

Ejecución: `validacion_20261016_01`. El análisis llegó hasta tablas nuevas de
`clean_validacion`; no promovió resultados al clean operativo ni al DW.

## Conservación

Se conservaron todos los registros y columnas originales. Cada tabla añade
derivadas `v_`, estados de calidad y referencias de origen. Los controles de
estructura, conteos, sumas de hashes y definiciones de vistas indican
`UNCHANGED` para `raw`, `clean`, `dwh` y `catalogo`, tanto al terminar la carga
como después del refinamiento de fechas de EDG.

Las tablas clean presentes en esta instalación se llaman `*_limpia_1`.
Se consultaron para comparar, sin renombrarlas ni modificarlas.

| Tabla de validación | Filas conservadas |
|---|---:|
| `mdi_homicidio_validacion_20261016_01` | 38.931 |
| `mdi_arma_validacion_20261016_01` | 69.688 |
| `mdi_desaparecido_validacion_20261016_01` | 75.461 |
| `edg_validacion_20261016_01` | 717.297 |
| `enemdu_validacion_20261016_01` | 1.750.008 |

Todas están en `clean_validacion`. No se eliminaron filas, incluidos los
candidatos a duplicados. No se imputaron cantidades, coordenadas o períodos.

## Hallazgos y decisiones pendientes

| Fuente | Resultado observado | Próxima decisión |
|---|---|---|
| Homicidios | 38.931 fechas interpretadas; 9.328 pares de coordenadas son (0,0). | No usar (0,0) como ubicación real. Evaluar análisis territorial por códigos/nombres. |
| Homicidios | 179 filas adicionales en grupos con igual hash de fila original. | Revisar unidad y posibles duplicados antes de reducir el conteo. |
| Armas | Cantidad numérica en 59.788 registros y ausente en 9.900. | No comparar cantidades de 2025 como si estuvieran informadas. |
| Armas | 7.343 filas adicionales en grupos con igual hash de fila original. | Validar si son repeticiones de carga o registros legítimos; no deduplicar automáticamente. |
| Desapariciones | 15 denuncias anteriores a la desaparición; 2.921 fechas de localización no aplicables. | Revisar casos temporales y definir universo de resolución sin excluir abiertos silenciosamente. |
| EDG | Las 717.297 fechas de fallecimiento quedaron interpretadas. El clean actual tiene 74.955 fechas nulas. | Validar la regla antes de promoverla al pipeline operativo. |
| EDG | 4 nacimientos posteriores al fallecimiento; 1.151 fechas de nacimiento no resueltas y 490 nulas. | Revisar por referencia al original, sin inventar fechas. |
| EDG | Variantes de numeración coalescidas sin conflictos observados. | Confirmar significado y unicidad por archivo con el diccionario. |
| ENEMDU | 1.639.725 períodos interpretados; 110.283 nulos de origen. | Se recupera cobertura antes perdida, pero no puede inventarse el período del resto. |
| ENEMDU | 1.726.487 correspondencias DPA únicas; 20.632 ambiguas y 2.889 no encontradas. | Revisar catálogo oficial; no asignar arbitrariamente los nombres ambiguos. |
| ENEMDU | Todos los factores de expansión son numéricos positivos. | Revisar universo, diseño y ponderación antes de estimar tasas oficiales. |

Los grupos de hash incluyen `source_file` cuando existe. Son candidatos de
duplicación del registro almacenado, no prueba de que se repita una persona
o un evento real. Los hashes no sustituyen la validación de identificadores.

## Recuperación temporal de ENEMDU

| Año interpretado | Registros | Meses distintos disponibles |
|---|---:|---:|
| 2018 | 59.350 | 1 |
| 2019 | 59.208 | 1 |
| 2020 | 30.646 | 1 |
| 2021 | 361.790 | 12 |
| 2022 | 358.096 | 12 |
| 2023 | 345.174 | 12 |
| 2024 | 341.394 | 12 |
| 2025 | 84.067 | 3 |
| Sin período | 110.283 | 0 |

Los 801.281 períodos escritos como meses españoles ya no se pierden por
convertirlos directamente a número. Las rondas de encuesta no tienen cobertura
temporal homogénea: no deben compararse como años completos ni sumarse sus
ponderadores entre meses sin definir primero el estimando.

## Respuestas que no son números exactos

En ENEMDU, las 887 edades sin conversión numérica exacta se explican por:

- 880 respuestas `98 y más` (con y sin espacios al inicio).
- 7 respuestas `No informa`.

Las primeras son una **categoría abierta**, no un error ni una edad exacta de
98 años. Pueden conservarse como intervalo/categoría tras validar el diccionario.

Las 12.841 respuestas de ingreso laboral no convertidas a número son:

- 9.028 `Gasta mas de lo que gana`.
- 3.813 `No informa`.

No se han convertido en cero ni en ingresos negativos. El estado técnico
`INVALID_OR_UNRESOLVED` significa "sin conversión numérica exacta", no que la
respuesta original sea necesariamente errónea. Las respuestas originales
permanecen disponibles para definir su tratamiento.

## Cruces candidatos

La comparación de cobertura encuentra 185 pares provincia-año compartidos entre
homicidios y ENEMDU, usando correspondencias DPA únicas para esta última. Es un
control exploratorio de disponibilidad, no un conjunto de observaciones ya
aprobadas para regresión o correlación.

Antes de analizar asociaciones se requiere:

1. Revisar cobertura mensual y períodos comparables.
2. Resolver o excluir justificadamente correspondencias territoriales ambiguas.
3. Definir indicadores y denominadores ENEMDU con diseño muestral.
4. Agregar cada fuente al mismo nivel antes de unirlas.
5. Separar asociación territorial de causalidad o vinculación de personas.

## Dónde consultar la evidencia

Ruta local: `reports/eda/validacion_20261016_01/`.

- `hallazgos.md`: detalle de estados, señales de revisión y candidatos de duplicación.
- `manifest.json` y `refinamiento.json`: estados de ejecución y revisiones de código.
- `conservacion.json` y `conservacion_refinamiento.json`: ambos `UNCHANGED`.
- Carpetas por fuente: perfiles completos de originales y derivadas, frecuencias,
  percentiles, histogramas, gráficos de ausencia y cobertura, y perfiles por archivo.
- `cruces_candidatos.csv`: pares provincia-año compartidos para cada combinación.

La primera consulta masiva de ENEMDU agotó su tiempo y se revirtió. La ejecución
se reanudó por bloques, reutilizando las cuatro fuentes ya confirmadas. EDG se
refinó después contrastando fechas día/mes/año con sus componentes originales.
Ambos pasos quedaron registrados; no se ocultó el intento fallido.

## Estado de aprobación

Esta es una salida de validación conservadora, no un clean final aprobado. Las
variables no seleccionadas para derivación se conservan en su estado original.
Se necesita revisar diccionarios, categorías abiertas, códigos, universos y
candidatos de duplicación antes de cambiar el modelo operativo o publicar
resultados científicos definitivos. No se actualizaron API, modelos ni dashboard.
