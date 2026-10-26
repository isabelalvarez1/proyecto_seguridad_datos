# Selección analítica mediante vistas normales

## Objetivo y alcance

Las vistas de `analitica` seleccionan variables de `clean` para tres análisis
candidatos del artículo: evolución territorial de la seguridad, perfil
demográfico y contexto socioeconómico. Son una selección inicial documentada,
no una aprobación automática de un modelo causal o de estimaciones oficiales.

No almacenan copias de registros, no eliminan columnas de clean y no modifican
raw, DW, cubos, API, dashboard ni modelos. No filtran filas ni deduplican
silenciosamente: cada vista conserva el número de registros de su fuente.

## Vistas de trabajo

| Vista normal | Contenido y finalidad |
|---|---|
| `analitica.v_homicidios` | Fecha, territorio, sexo, edad/grupo, tipo de muerte, arma y contexto del hecho. |
| `analitica.v_armas` | Registros territoriales, clase/objeto, cantidades observadas y disponibilidad. |
| `analitica.v_desapariciones` | Fecha, territorio, demografía, situación y duraciones observables. |
| `analitica.v_defunciones` | Mortalidad por fecha, territorio, sexo, edad con unidad y causas; campos condicionados de circunstancias/autopsia. |
| `analitica.v_enemdu` | Período, territorio, demografía, educación, pobreza, ingresos y diseño de encuesta. |
| `analitica.v_catalogo_provincias` | Auxiliar de 24 códigos provinciales con correspondencia única, no un conjunto de casos de estudio. |

La unidad sigue siendo un **registro de fuente**, no necesariamente una persona
única o un evento único. En ENEMDU son registros de rondas: no sumar personas
entre meses como si fueran población distinta.

## Qué se incluye y qué se aparta

Los campos tienen roles explícitos:

- **Principal:** responde a alguno de los análisis candidatos.
- **Condicional:** útil en un período/subgrupo o pendiente de homologación; no
  debe usarse automáticamente sobre toda la población.
- **Control:** explica disponibilidad, consistencia o interpretación de otro campo.
- **Diseño muestral:** ponderador, estrato y UPM necesarios para evaluar ENEMDU.
- **Procedencia:** versión clean y archivo cuando existe; no son predictores.

Las numeraciones de EDG y sus variantes, identificadores individuales, copias
`*_original` y referencias internas se apartan de las vistas. Se conservan en
clean para auditoría. Las coordenadas puntuales quedan fuera del alcance
territorial inicial, que utiliza provincia/cantón.

Una variable sin valores en la versión actual no entra para fabricar información
con imputación. Una variable con más de 90% de nulos **no se descarta por esa
única razón**: primero hay que revisar si aplica a un subgrupo o a otra versión.
Por ejemplo, circunstancias de mortalidad externa pueden ser pertinentes en
su universo aunque estén ausentes en la mayor parte de defunciones.

## Faltantes e imputación

En esta fase descriptiva **no se aplican medias, medianas, modas, ceros ni
modelos para completar observaciones**. El EDA justifica distinguir ausencias
estructurales, no aplicabilidad, censura y respuestas no numéricas; no demuestra
por sí solo un mecanismo de ausencia que autorice imputación estadística.

Dos recuperaciones sí son verificables y se hacen al consultar:

1. **Duración de localización:** diferencia entre fechas observadas, cuando la
   localización no antecede a la desaparición. `duracion_origen` distingue la
   comprobación del valor reportado del cálculo cuando no estaba informado.
   No completa fechas ni casos abiertos. No presupone que todo caso localizado
   equivalga a resolución bajo una misma definición.
2. **Provincia de ENEMDU:** si falta el nombre en clean, se utiliza un código
   provincial que tiene una sola correspondencia en el catálogo. Esto no decide
   el cantón ambiguo. `provincia_origen` identifica la resolución por referencia;
   `dpa_estado` conserva el problema original de cantón.

Son **derivaciones deterministas**, no imputación estadística. Se conserva:

- La edad exacta nula para «98 y más». El grupo `65+` sí es conocido por su
  límite inferior, sin fingir una edad puntual para calcular medias.
- La unidad de edad en EDG; meses/días/horas no reciben la media de años.
- El ingreso laboral nulo con su estado cuando la respuesta no es un monto.
- La cantidad de armas ausente en 2025, sin sustituirla por uno o por otro año.
- Autopsias codificadas pendientes, sin interpretar 1/2/9 por intuición.
- Pobreza desconocida como nula: no se transforma en «no pobre».

Cada reporte incluye `decisiones_imputacion.csv` con decisión y justificación
por campo. Si se desarrolla un modelo predictivo, la imputación se evaluará
dentro del entrenamiento y la validación temporal, sin utilizar el conjunto
de prueba para estimar parámetros.

## Ejecutar y verificar

Desde la raíz con PostgreSQL y clean disponibles:

```powershell
python -m scripts.create_analytic_views --plan
python -m unittest tests.test_analytic_views -v
python -m analysis.check_analytic_sql
python -m scripts.create_analytic_views
```

El publicador crea únicamente vistas normales de nombres definidos en
`utils/analytic_views.py`. No reemplaza un objeto existente ajeno al contrato.
`CREATE OR REPLACE VIEW` mantiene el contrato de columnas; un cambio incompatible
exigirá una migración explícita, no eliminación automática con CASCADE.

Los ensayos SQL usan solo SELECT y casos de control. Comprueban, entre otros,
que una pobreza desconocida no se vuelva cero, que no se adivinen autopsias y
que los intervalos negativos no se publiquen como duraciones observadas.

## Reportes para decidir variables

Resultado de la primera selección consolidada: [resumen de selección analítica](resultados_seleccion_analitica.md).

`reports/analitica/<run_id>/` contiene:

- `contrato_vistas.json`: finalidad, unidad de observación, SQL y definiciones.
- Por vista, `seleccion_variables.csv`: **todas las columnas** de su tabla clean,
  cobertura, decisión y motivo; incluye las que no se seleccionaron.
- Por vista, `diccionario_vista.csv`: alias, rol, tipo, cobertura y tratamiento.
- `decisiones_imputacion.csv`: decisión por campo.
- `recuperaciones_y_controles.json`: recuperación determinista y verificaciones.
- `conservacion.json`: controles de estructura, conteos y contadores DML; no son
  hashes completos de contenido. El código solo escribe DDL en `analitica`.
- `resultado.md` y `manifest.json`: resumen y estado de ejecución.

Las coberturas de estos archivos describen la instantánea de ejecución. Las
vistas normales cambian sus resultados cuando cambian sus fuentes; para las
figuras definitivas hay que registrar versión de datos, filtros y código.

## Consultas iniciales

```sql
SELECT anio, provincia, COUNT(*) AS registros
FROM analitica.v_homicidios
GROUP BY anio, provincia
ORDER BY anio, registros DESC;

SELECT periodo, provincia,
       COUNT(*) AS registros_encuesta,
       COUNT(pobreza_binaria) AS respuestas_pobreza_validas
FROM analitica.v_enemdu
WHERE apto_contexto_provincia_periodo
GROUP BY periodo, provincia;
```

No son tasas poblacionales. Para estimarlas se deben fijar universo, ronda,
ponderación, diseño y denominadores. Las distintas coberturas mensuales tampoco
permiten comparar todos los años como si fueran completos.

## Dependencia con futuras cargas clean

Las vistas están ligadas a los objetos clean. Las actualizaciones de datos en
esas tablas se ven al volver a consultar; no necesitan REFRESH. Si un cliente
importó datos, debe volver a solicitarlos.

El publicador de clean reenlaza las vistas administradas al sustituir tablas,
dentro de la misma transacción y manteniendo los OID de las vistas. Se detiene
ante dependencias ajenas o contratos incompatibles. Esto evita que queden
leyendo inadvertidamente una tabla archivada. Después, el flujo de actualización
publica una carga nueva del mart web para que la aplicación vea los resultados.
