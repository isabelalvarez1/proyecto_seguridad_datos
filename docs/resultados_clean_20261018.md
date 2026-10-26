# Resultado de publicación de clean — 18 de octubre de 2026

La ejecución `clean_20261016_01` terminó en estado **PUBLISHED** el 18 de octubre
de 2026. Su identificador se mantuvo para enlazar el trabajo iniciado con la
validación `validacion_20261016_01`; la fecha efectiva consta en el manifiesto.

## Tablas nuevas y versiones anteriores

| Tabla actual | Filas | Referencia anterior conservada |
|---|---:|---|
| `clean.homicidio_limpia` | 38.931 | `clean.homicidio_limpia_1` |
| `clean.mdi_arma_limpia` | 69.688 | `clean.mdi_arma_limpia_1` |
| `clean.mdi_desaparecido_limpia` | 75.461 | `clean.mdi_desaparecido_limpia_1` |
| `clean.edg_limpia` | 717.297 | `clean.edg_limpia_1` |
| `clean.enemdu_limpia` | 1.750.008 | `clean.enemdu_limpia_1` |

Las cinco tablas se construyeron primero en `clean_preparacion`, se verificaron
y se publicaron juntas. No quedaron tablas de esta ejecución en preparación.
No se reemplazaron ni renombraron las tablas `_1`, y no se eliminaron filas.

Los controles reconstruyeron cada registro original desde sus columnas
conservadas: **cero valores originales alterados** y mismos conteos y sumas de
hashes de contenido que raw. Esto no significa que los campos limpios sean
idénticos a los originales, sino que las transformaciones son auditables.

## Cambios aplicados

### ENEMDU

- **1.639.725 períodos** interpretados, incluidos los meses escritos como texto.
- **110.283 períodos ausentes de origen** permanecen nulos; no se inventaron años.
- **880 edades «98 y más»** se conservan como categoría abierta, con límite
  inferior y marca de censura; no se usan como edades exactas de 98.
- **9.028 respuestas «Gasta mas de lo que gana»** y **3.813 «No informa»** en
  ingreso laboral se clasifican aparte; no se convierten a cero ni a números negativos.
- **20.632 correspondencias DPA ambiguas** y **2.889 no encontradas** permanecen
  señaladas, sin asignar nombres arbitrarios.
- Todos los factores de expansión interpretados son positivos. Esto no sustituye
  la revisión del diseño muestral ni autoriza por sí solo estimaciones oficiales.

### Defunciones

- Las **717.297 fechas de fallecimiento** se conservaron interpretadas.
- Las variantes de numeración se preservan y se coalescen sin descartar columnas.
- Se conserva la unidad de edad: horas, días y meses no se interpretan como años.
- **4 nacimientos posteriores al fallecimiento** quedan marcados para revisión.
- Autopsia y causas conservan sus códigos pendientes de diccionario.

### Homicidios, armas y desapariciones

- Nombres territoriales normalizados con las reglas verificadas, incluido Durán.
- **9.328 pares (0,0)** de homicidios dejan de utilizarse como coordenadas limpias;
  el valor original y el motivo permanecen disponibles.
- Los pares incompletos o fuera de rango global tampoco se usan como coordenadas
  limpias. No se imputan ubicaciones ni se intercambian ejes automáticamente.
- **9.900 cantidades de armas no informadas** permanecen nulas.
- Se conservan estados de desaparición distintos y fechas no aplicables, sin
  inventar equivalencias entre encontrado, localizado y fallecido.
- No se eliminaron los candidatos de duplicación: su tratamiento requiere
  validar identificadores y unidad de observación.

## Qué se conservó fuera de clean

- La comparación completa previa a la publicación indicó **UNCHANGED** para
  los objetos anteriores de raw, clean, DW y catálogo.
- La auditoría posterior comprobó métricas de las cinco tablas nuevas y volvió
  a comparar contenido, estructura y vistas de **raw, DW y catálogo**: **UNCHANGED**.
- Las tablas anteriores de clean conservaron sus identidades y contenido
  comprobado antes del intercambio; no hubo escrituras sobre ellas.
- No se ejecutaron cargas de hechos/dimensiones, refrescos de cubos, entrenamiento
  ni modificaciones de API o dashboard.

El cubo de homicidios sigue sumando **38.752**, mientras el nuevo clean conserva
**38.931** registros originales. Es una diferencia esperada de versiones y
tratamientos: el DW aún corresponde a la carga anterior, no al nuevo clean.

## Evidencia e instrucciones

Ruta local: `reports/clean/clean_20261016_01/`.

- `manifest.json`: estado PUBLISHED, fuentes y huellas del código.
- `resultado.md`: resumen generado por el proceso.
- `conservacion.json`: conservación e identidad de los objetos anteriores.
- `postpublication_audit.json`: auditoría posterior en estado UNCHANGED.
- Por fuente: `resumen.json`, `mapeo_columnas.csv`, `estados.csv` y `cobertura_anual.csv`.

En pgAdmin, actualizar el árbol del esquema `clean` para ver las tablas sin `_1`.
Para una revisión pequeña de ENEMDU:

```sql
SELECT periodo, periodo_original, periodo_estado,
       p03, p03_estado, edad_censurada, edad_limite_inferior
FROM clean.enemdu_limpia
LIMIT 20;
```

Las columnas `*_original` y las referencias de ejecución sirven para auditoría;
no son variables predictoras por defecto. Los campos `*_estado` deben utilizarse
para definir exclusiones, universos y limitaciones de cada análisis.

## Próxima etapa

Revisar variables, diccionarios y cobertura del nuevo clean; definir una matriz
de cruces por territorio/período y la pregunta del artículo. La publicación
no resuelve automáticamente categorías ambiguas, duplicación, representatividad
de encuesta o causalidad. Actualizar el DW requiere una decisión posterior
y adaptar su contrato de carga a los nuevos estados y tratamientos.
