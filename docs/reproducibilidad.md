# Reproducibilidad y uso científico

## Qué registrar para cada experimento

1. Fuente oficial y URL de descarga de cada conjunto de datos.
2. Fecha de descarga, período cubierto y versión del catálogo geográfico.
3. Conteo de filas antes y después de limpieza, deduplicación y carga.
4. Valores ausentes, reglas de exclusión y homologaciones aplicadas.
5. Commit utilizado, versiones instaladas, parámetros y partición de evaluación.

El repositorio contiene la implementación, pero no distribuye los archivos
fuente, la base PostgreSQL ni una instantánea de los modelos. Las dependencias
de `requirements.txt` indican mínimos, no un entorno bloqueado. Para reportar
un experimento, conservar también su salida de `python -m pip freeze`.

## Cobertura observada en la base de desarrollo

Estos resultados son controles de una carga local, no constantes del sistema:

| Control | Resultado observado |
|---|---:|
| Hechos de homicidio / suma del cubo | 38.752 |
| Filas del cubo combinado provincia-año | 92 |
| Suma de homicidios del cubo combinado | 9.511 |
| Durán, Guayas, agregado en todo el historial | 1.790 |

Homicidios abarca 2014–2025; 2025 tiene registros hasta noviembre. Para comparar
años completos se utilizó 2014–2024 (30.397 casos); la mera presencia de meses
no garantiza por sí sola exhaustividad de la fuente.

El cruce seguridad-economía tiene años compartidos 2018, 2019, 2021 y 2022.
Es una unión interna: la ausencia de un par provincia-año no debe interpretarse
como cero homicidios o cero pobreza.

## Agregaciones e indicadores

- Contar filas de un cubo no equivale a sumar casos: varias observaciones
  originales pueden estar agrupadas en una fila.
- `personas_encuestadas` representa registros de encuesta agregados, no
  población nacional ni necesariamente personas únicas entre períodos.
- Los porcentajes de pobreza/empleo implementados son proporciones sin
  ponderación sobre los registros analizados. No deben presentarse como tasas
  oficiales ENEMDU sin revisar universo, ponderadores y diseño muestral.
- Los ingresos medios deben calcularse desde los registros o con denominadores
  válidos; promediar medias de grupos de distinto tamaño puede sesgar el resultado.
- Las tasas por 100.000 habitantes necesitan población oficial comparable.
- Categorías `SIN_DATO` y códigos de autopsia sin verificar deben documentarse.
- Las vistas de defunciones/desapariciones utilizan uniones internas a fechas:
  los registros sin alguna fecha exigida pueden no aparecer en sus cubos.
  Por eso no debe suponerse igualdad entre todos los hechos y sus cubos.

La normalización de Durán unifica `DURAN`/`DURÁN` para las cargas futuras.
La corrección aplicada a la dimensión existente se restringió a Guayas; otras
combinaciones territoriales inconsistentes requieren validación de la fuente.

## Predicción y correlación

Los entrenamientos actuales emplean particiones aleatorias. Antes de presentar
sus métricas como evidencia predictiva definitiva hay que evaluar por tiempo,
evitar fuga de información y alinear las variables de entrenamiento e inferencia.
En particular, revisar el acumulado del año y el significado de los lags de
3/6 meses, así como meses ausentes y horizontes futuros sin observaciones.

Una correlación agrupada de provincias y años es exploratoria: no demuestra
causalidad ni controla diferencias territoriales, temporales o de población.

## Lista de verificaciones de una actualización

- Comparar sumas entre hechos, cubos, vistas y API para el mismo universo.
- Contar pares provincia-año únicos antes de cruzar fuentes.
- Revisar claves sin correspondencia y fechas faltantes.
- Ejecutar pruebas geográficas y guardar los resultados del experimento.
- Refrescar cubos tras recargar hechos y actualizar Power BI tras el refresco.
