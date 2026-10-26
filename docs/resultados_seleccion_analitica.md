# Resultado de selección analítica

Ejecución consolidada: `seleccion_20261018_02`, finalizada correctamente.
Se crearon **vistas normales** en `analitica`, no tablas nuevas de casos ni
vistas materializadas. Las fuentes clean y las capas existentes se conservan.

## Qué consultar ahora

| Vista | Registros | Campos (incluyen controles/procedencia) |
|---|---:|---:|
| `analitica.v_homicidios` | 38.931 | 22 |
| `analitica.v_armas` | 69.688 | 19 |
| `analitica.v_desapariciones` | 75.461 | 20 |
| `analitica.v_defunciones` | 717.297 | 24 |
| `analitica.v_enemdu` | 1.750.008 | 35 |

La auxiliar `analitica.v_catalogo_provincias` contiene 24 correspondencias
únicas de códigos provinciales y nombres. No representa registros de personas.

No se filtró un período de estudio ni se eliminaron candidatos a duplicación.
Una fila sigue siendo un registro de la fuente. El universo final del artículo
se debe definir con fechas, territorio, estados y denominadores explícitos.

## Variables incluidas

- **Homicidios:** tiempo, provincia/cantón, sexo, edad y grupo, tipo de muerte,
  arma y contexto del hecho. Detalle de arma y presunta motivación tienen uso
  condicionado por cobertura/interpretación.
- **Armas:** tiempo, territorio, clase y objeto, cantidad y disponibilidad;
  delito y tipo de delito se mantienen con sus límites de cobertura.
- **Desapariciones:** tiempo, territorio, sexo/edad, situación original reportada,
  fechas y duración observable, con controles temporales.
- **Defunciones:** fecha y territorio, sexo, edad con unidad, causas y agrupación;
  circunstancias externas y autopsia requieren su universo y diccionario.
- **ENEMDU:** período, geografía, área, sexo/edad, educación, ingresos, pobreza,
  contexto laboral y campos de diseño muestral. No se ha estimado una tasa oficial.

Las numeraciones de EDG y sus tres variantes no aparecen en la vista de
defunciones: se reservaron para auditoría en clean. Lo mismo ocurre con copias
originales e identificadores individuales. Estrato y UPM sí se mantienen para
el diseño de encuesta; no se proponen como predictores por defecto.

Las partes de fechas y representaciones redundantes se sustituyen en las
vistas por fechas/componentes derivados verificados. Otras agrupaciones de causa
se reservan para preguntas específicas. Variables de otros universos, como
mortalidad materna, no se califican como inútiles por sus nulos globales.

## Recuperaciones verificadas, sin imputación estadística

| Operación | Resultado | Qué no se hizo |
|---|---:|---|
| Calcular duración con fechas observadas | 5.853 registros adicionales | No completar fechas ni casos abiertos. |
| Resolver provincia por código provincial único | 22.129 registros | No decidir cantones ambiguos ni usar la provincia más frecuente. |
| Mantener provincia pendiente | 1.392 registros | No inventar nombres para códigos sin correspondencia. |
| Agrupar edades de horas/días/meses conocidas | 23.877 registros menores de un año | No asignarles una edad exacta en años. |

En ENEMDU, «98 y más» permanece sin edad puntual; sí puede agruparse en `65+`
por su límite inferior. Las respuestas de ingreso no numéricas y pobreza
desconocida permanecen nulas en los campos numéricos respectivos, con estado.

No se adivinaron códigos de autopsia ni se publicaron duraciones negativas.
Las 5.853 duraciones calculadas se distinguen de las reportadas y comprobadas.

## Decisión sobre imputación

No se aplicó media, mediana, moda ni imputación por modelos. La fase actual es
descriptiva y de selección; todavía no existe un modelo/estimando aprobado ni
una evaluación del mecanismo de ausencia que justifique esos tratamientos.
Imputar globalmente podría mezclar no aplicabilidad, versiones de archivo,
censura, no respuesta y respuestas cualitativas.

El informe `decisiones_imputacion.csv` contiene una decisión para cada campo.
Esto no descarta toda imputación futura: un modelo específico podría compararla
dentro del entrenamiento y la validación temporal. No corresponde modificar
permanentemente los valores observados para facilitar una gráfica.

## Dónde revisar variable por variable

Ruta local:

```text
reports/analitica/seleccion_20261018_02/
```

En la carpeta de cada vista:

1. **`seleccion_variables.csv`**: todas las columnas de su fuente clean, cobertura,
   decisión de inclusión/exclusión y motivo.
2. **`diccionario_vista.csv`**: cada campo publicado, su rol, tipo, cobertura y
   tratamiento de faltantes.

En la raíz:

- `resultado.md`: resumen generado.
- `decisiones_imputacion.csv`: decisiones de faltantes por campo.
- `contrato_vistas.json`: SQL, finalidad y unidad de observación.
- `recuperaciones_y_controles.json`: resultados verificables de las derivaciones.
- `conservacion.json`: estado `UNCHANGED` de identidades, estructura, conteos,
  definiciones y contadores DML de las capas anteriores; no es un hash de contenido.
- `manifest.json`: estado `COMPLETED` y huellas del código.

## Ver en pgAdmin

Actualizar el árbol de esquemas y abrir **analitica → Views/Vistas**. Ejemplo:

```sql
SELECT anio, provincia, sexo, edad_anios, grupo_edad, tipo_muerte
FROM analitica.v_homicidios
LIMIT 20;

SELECT periodo, provincia, provincia_origen, canton, dpa_estado,
       pobreza, ingreso_per_capita
FROM analitica.v_enemdu
LIMIT 20;
```

Los faltantes deben informarse como tales, no reemplazarse por ceros en las
visualizaciones. Las consultas futuras reflejan las fuentes; los reportes
describen esta instantánea y deben regenerarse al cambiar los datos.

## Alcance conservado

No se actualizaron raw, clean, catálogo, DW, cubos, API, modelos ni dashboard.
La próxima publicación física de clean debe coordinar estas dependencias:
su publicador actual se detendrá ante vistas dependientes para evitar que
queden enlazadas inadvertidamente a tablas archivadas.

El siguiente trabajo es definir períodos comparables, universos e indicadores
del artículo y evaluar los cruces con esta selección. Las vistas no realizan
por sí solas ponderación de encuesta, ajuste poblacional o inferencia causal.
