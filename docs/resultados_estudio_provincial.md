# Resultados iniciales del estudio provincial

Ejecución consolidada: `provincial_20261019_02`, estado **COMPLETED**.
Es un experimento retrospectivo exploratorio, no un modelo aprobado para la API
ni una estimación provincial oficial de ENEMDU.

## Qué se construyó

- Panel descriptivo de 168 pares provincia-año (2018–2024), de los cuales 162
  tienen registros y contexto observado para el cruce exploratorio.
- Cohorte de comparación predictiva de 115 pares (2020–2024).
- 69 predicciones provincia-año fuera de tiempo por modelo, en 2022, 2023 y 2024.
- Dos referencias sencillas y dos familias de modelos, cada una con/sin contexto.
- Sensibilidad a hashes distintos y a excluir diciembre 2020 de ENEMDU.
- Figuras, métricas por provincia/año y proyecciones experimentales de 2025.

Las filas sin registros no se convirtieron en cero. Se conservaron motivos de
exclusión y no se imputaron características para aumentar artificialmente la muestra.

## Resultado principal: una referencia sencilla funcionó mejor

MAE: error absoluto medio en **registros por provincia-año**. Menor es mejor.

| Método | MAE conjunto 2022–2024 | MAE final 2024 |
|---|---:|---:|
| Año anterior | 111,16 | 68,30 |
| Promedio de dos años anteriores | 127,85 | 54,91 |
| RF con historial | 219,73 | 298,29 |
| RF con historial y contexto | 219,52 | 298,23 |
| Poisson con historial | 251,15 | 450,18 |
| Poisson con historial y contexto | 254,70 | 436,20 |

La referencia del año anterior tuvo el menor error agregado temporal. En 2024,
la media de los dos años anteriores fue mejor entre las alternativas evaluadas.
Esto no autoriza elegir retrospectivamente una referencia distinta para cada año.

Los modelos y esta configuración no superaron las referencias en la cohorte
común. El resultado depende del corto entrenamiento disponible y de cambios
importantes en la serie; no demuestra que todo modelo predictivo sea inútil.

No se cambiaron hiperparámetros después de ver 2024 para mejorar su puntuación.
Estas métricas tampoco son directamente comparables con las de los modelos
anteriores del repositorio: cambian la unidad, los datos y la evaluación.

## ¿Mejora añadir pobreza e ingreso?

No se observó una mejora consistente en el experimento principal:

- En Poisson, el contexto empeora el MAE agregado de 251,15 a 254,70.
- En RF, lo reduce apenas de 219,73 a 219,52.
- En 2024, Poisson mejora algo con contexto, pero su error sigue por encima
  de las referencias sencillas.
- Los intervalos exploratorios de las comparaciones principales incluyen cero.
- Las sensibilidades modifican los resultados; no justifican afirmar un aporte
  socioeconómico robusto ni un efecto causal.

Esto no significa que pobreza o ingreso no tengan relación con seguridad.
Significa que **estos predictores, fuentes, rezagos, modelos y muestra no
demostraron una mejora predictiva robusta frente al historial**.

## Hallazgo metodológico que condiciona el artículo

INEC diferencia la ENEMDU anual, que permite mayor desagregación provincial,
de las rondas mensuales/trimestrales. También indica que no produjo una anual
2020 por cambios de levantamiento.

Nuestro agregado de diciembre se conserva como experimento, pero no debe
presentarse automáticamente como tasa provincial anual oficial. Un tamaño de
muestra o un diagnóstico Kish aceptable no verifica ese dominio de estimación.

Además, faltan población provincial comparable, deflactor de ingreso y auditoría
de disponibilidad histórica de cada predictor. El contexto se rezagó dos años,
pero no se han reconstruido fechas reales de publicación o versiones anteriores.

Fuentes oficiales consultadas:

- [ENEMDU anual](https://www.ecuadorencifras.gob.ec/enemdu-anual/).
- [Estadísticas laborales ENEMDU](https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/).

## Qué significa para la predicción

Sí se construyó y ejecutó una evaluación predictiva. El resultado no respalda
promover ahora los modelos de ML ensayados al dashboard. La referencia simple
debe mantenerse como requisito mínimo de cualquier siguiente evaluación.

Se exportaron proyecciones de 2025 para 23 provincias como ejercicio retrospectivo.
No son una predicción nueva de 2026 ni están validadas contra un 2025 completo.
La provincia sin historial completo no recibió una predicción inventada.

## Dónde revisar

```text
reports/investigacion/provincial_20261019_02/
```

- `resultado.md` y `protocolo.json`: resumen y decisiones del experimento.
- `panel_descriptivo_y_exclusiones.csv`: cuadrícula completa y elegibilidad.
- `cohorte_registros_contexto_lag2.csv`: datos y exclusiones de la comparación principal.
- `folds.csv`: límites temporales y tamaños reales de entrenamiento/prueba.
- `predicciones_fuera_de_tiempo.csv`: observados y predichos, por modelo y escenario.
- `metricas.csv`, `metricas_por_anio.csv`, `metricas_por_provincia.csv`: errores.
- `comparacion_pareada_contexto.csv`: aporte incremental y bootstrap exploratorio.
- `proyeccion_retrospectiva_2025.csv`: proyecciones etiquetadas como no operativas.
- `elegibilidad_proyeccion_2025.csv`: distingue falta de predictores de falta de resultado futuro.
- `modelos_experimentales/`: archivos separados de los modelos operativos.
- Figuras PNG y manifiesto con versiones y huellas del código/CSV.

## Próximas implementaciones recomendadas

1. **Prioridad metodológica:** obtener indicadores provinciales anuales oficiales
   o verificar dominios, ponderadores, versiones y errores de diseño de los archivos locales.
2. Incorporar población provincial oficial por año. No calcular riesgo por habitante
   usando el tamaño de muestra de la encuesta.
3. Confirmar unidad de registro y reglas de duplicación con documentación de la fuente.
4. Registrar fechas de publicación y revisiones para validar disponibilidad histórica real.
5. Repetir el análisis con esos insumos. Una alternativa adicional es evaluar
   historial más amplio sin contexto, con un protocolo nuevo que declare los
   años ya observados; no reajustar contra 2024 como si siguiera intacto.
6. Solo después, definir endpoints y el dashboard Vue con indicadores y modelos
   que hayan pasado los criterios definidos.

La implementación consultó PostgreSQL en READ ONLY y guardó resultados locales.
No actualizó datos, vistas, DW, cubos, API, dashboard ni modelos operativos.
