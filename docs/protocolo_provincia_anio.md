# Protocolo ejecutado: provincia-año y evaluación predictiva

## Preguntas

1. ¿Cómo se distribuyen y evolucionan los registros de homicidio por provincia?
2. ¿Qué asociaciones exploratorias presentan con el contexto socioeconómico?
3. ¿Añadir contexto previo mejora la predicción frente a utilizar solo historial?

No se plantea identificar un efecto causal de pobreza ni riesgo individual.
La unidad es provincia-año y el resultado es un conteo de registros conservados.
Población y unidad de observación definitiva requieren documentación adicional.

## Ajuste metodológico tras consultar INEC

La [página oficial ENEMDU anual](https://www.ecuadorencifras.gob.ec/enemdu-anual/)
explica que el agregado anual permite mayor desagregación, incluida provincial,
y que no se produjo una ENEMDU anual 2020 por incompatibilidad de levantamientos.
La [página mensual](https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/)
documenta cambios metodológicos entre 2020 y mayo 2021 y vincula la
[nota técnica](https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2021/Nota_tecnica/202106_Nota_tecnica_ENEMDU.pdf).

Por tanto, disponer de registros de una provincia en diciembre no demuestra
que su estimación sea representativa a nivel provincial. El experimento actual
usa razones ponderadas de diciembre **como variables exploratorias**, no como
tasas provinciales anuales oficiales. Antes de usar ese cruce como evidencia
sustantiva del artículo deben verificarse dominios y versiones o incorporarse
indicadores provinciales anuales validados.

## Fuentes e integración

- `clean.homicidio_limpia`: conteos por provincia/año y hashes distintos para
  sensibilidad; no se elimina ninguna fila en PostgreSQL.
- `analitica.v_enemdu`: registros de diciembre, respuestas de pobreza/ingreso,
  pesos y diagnósticos de diseño disponibles.
- Catálogo provincial de la capa analítica: 24 provincias con código único.
- Comparaciones auxiliares de armas y EDG: agregadas por separado y unidas
  uno a uno; no se suman como casos independientes de homicidio.

Toda extracción se ejecuta en una transacción PostgreSQL **READ ONLY, REPEATABLE
READ**, con comprobación de identidad/definiciones y versión de clean. No hay
DDL ni DML de datos dentro del estudio. Los resultados se guardan localmente.

## Cobertura y ausencias

- Serie histórica de homicidios: 2014–2024 con doce meses nacionales observados.
- 2025 tiene once meses observados y no se usa como resultado anual de evaluación.
- Contexto descriptivo: diciembre 2018–2024.
- Cuadrícula de 168 pares (24 provincias × 7 años), con 162 cruces observados.
- Ausencia de filas provincia-año se mantiene como no observada, no como cero.
- Doce meses con registros a nivel nacional no certifican exhaustividad territorial.
- No se utiliza el número de encuestados como población para tasas de homicidio.

La pobreza experimental es `sum(w*y)/sum(w)` sobre respuestas conocidas; el
ingreso es `sum(w*ingreso)/sum(w)` sobre respuestas válidas de ese indicador.
No se mezclan denominadores. Se conserva tamaño de muestra, diseño incompleto,
estratos, UPM y tamaño efectivo de Kish. Este último **no es** error estándar
del diseño ni certificación del dominio provincial. El ingreso permanece nominal.

## Predicción y disponibilidad temporal

Se predice el conteo del año t con:

- Homicidios t−1 y t−2 (log1p).
- Tendencia de año conocida.
- Provincia como categoría.
- En la variante contextual: pobreza e ingreso de diciembre t−2, este último en log1p.

Los rezagos son uniones por año calendario, no `shift` que salte períodos ausentes.
No se introduce el acumulado del propio año que se quiere predecir.

Se eligió un rezago socioeconómico de dos años para evitar contexto contemporáneo.
**No están auditadas las fechas de publicación ni las revisiones históricas.**
La instantánea actual no permite afirmar qué información estaba publicada en
una fecha pasada concreta. Esto es un pseudopronóstico retrospectivo, no un
backtest operativo de disponibilidad real.

## Comparación justa

Se utiliza la misma cohorte completa y los mismos años de entrenamiento para
historial y contexto: 115 pares, 2020–2024, de 23 provincias. Los años anteriores
sirven para construir rezagos; no se añaden como filas de entrenamiento a un
solo modelo de la comparación pareada. Esto limita el entrenamiento y debe
declararse al interpretar el rendimiento.

No hay imputador: se exportan todas las exclusiones y sus motivos. No se pierden
registros de las fuentes ni se convierten nulos en ceros.

| Año evaluado | Entrenamiento | Filas entrenamiento | Filas prueba |
|---|---|---:|---:|
| 2022 | 2020–2021 | 46 | 23 |
| 2023 | 2020–2022 | 69 | 23 |
| 2024 | 2020–2023 | 92 | 23 |

2022–2023 son evaluaciones temporales de desarrollo; 2024 se reservó como
evaluación final. Los hiperparámetros se fijaron antes de observar métricas.
No se ajustaron posteriormente para conseguir mejor resultado en 2024.

## Modelos y referencias

Referencias:

1. Mismo valor del año anterior.
2. Media aritmética de los dos años anteriores (pronóstico, no imputación de datos).

Modelos:

- Poisson regularizado, alpha=1, máximo 5.000 iteraciones.
- Random Forest, 200 árboles, profundidad 4, mínimo 5 observaciones por hoja,
  semilla 42; comprobación secundaria.

Cada familia se evalúa con historial y con historial+contexto. Escalado y
codificación se ajustan únicamente al entrenamiento mediante pipelines. No se
utilizan predicciones para rellenar los datos ni se modifica el objetivo observado.

Poisson se usa como regresión predictiva de conteos sin offset de población;
no se reportan coeficientes causales ni se asume validación inferencial de
equidispersión. RF no tiene garantizada extrapolación ante cambios de magnitud.

## Evaluación y sensibilidad

- MAE y RMSE, globales, por año y por provincia.
- WAPE para error relativo agregado; puede estar dominado por provincias grandes.
- R² como métrica secundaria: no equivale a porcentaje de aciertos.
- Comparación pareada de MAE con bootstrap de errores por provincia, semilla 42,
  1.000 réplicas. No incorpora diseño ENEMDU, cambios de régimen o incertidumbre
  de reentrenamiento, y no es evidencia causal.
- Sensibilidad con conteos de hashes distintos, sin aprobar deduplicación de personas/eventos.
- Sensibilidad excluyendo la ronda ENEMDU diciembre 2020; cambia los folds
  disponibles y no elimina toda influencia de 2020 en el historial de homicidios.

Se exportan proyecciones experimentales de 2025 para las 23 provincias con
predictores completos; no se validan contra enero–noviembre como si fuera el
año completo. No se genera 2026 porque falta el año 2025 completo para el lag.

## Ejecutar

```powershell
python -m unittest tests.test_provincial_study -v
python -m analysis.run_provincial_study
```

La salida va a `reports/investigacion/<run_id>/`, con protocolo, datos agregados,
exclusiones, folds, predicciones, métricas, figuras, modelos experimentales y
huellas del código/CSV. No sustituye `ml/modelos/` ni lo que carga la API.

La ejecución consolidada y sus conclusiones están en
[resultados del estudio](resultados_estudio_provincial.md).
