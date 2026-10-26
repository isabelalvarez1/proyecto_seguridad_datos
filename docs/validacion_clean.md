# EDA y limpieza de prueba, sin actualizar el DW

## Alcance

El comando `python -m analysis.run_clean_validation` consulta `raw` y crea
tablas nuevas por ejecución en el esquema fijo `clean_validacion`.
No ejecuta los cargadores operativos ni los refrescos de cubos. No modifica
`raw`, el `clean` existente, `dwh`, la API, el dashboard ni los modelos.

No es todavía una sustitución aprobada de `clean`: es una capa conservadora
para revisar y decidir las transformaciones finales con evidencia.

## Diseño de las tablas

Cada tabla conserva **todas las filas y todas las columnas originales**, con
sus nombres y tipos. No aplica deduplicación, eliminación de outliers ni
imputación. Las columnas derivadas empiezan por `v_`:

- `v_periodo`: ENEMDU `YYYYMM`, a partir de formato numérico o mes español.
- `v_fecha_*`: fechas interpretadas sin depender de DateStyle de PostgreSQL.
- `v_edad`, `v_p03`, `v_cantidad`, `v_fexp`, `v_ingpc`, etc.: números interpretados.
- `v_edad_anios`: edad solo cuando la unidad en años está identificada, si la
  fuente tiene columna de unidad. Días, horas y meses no se confunden con años.
- Variables categóricas seleccionadas: recorte de espacios y mayúsculas, sin
  inventar equivalencias de códigos ni unificar estados semánticamente distintos.
- `v_provincia`/`v_canton` y campos equivalentes: normalización compartida,
  incluyendo Durán. ENEMDU utiliza solo correspondencias únicas del DPA.
- `v_numeracion`: coalescencia de variantes EDG, conservando las tres originales
  y una señal si se contradicen.

Los estados `*_estado` separan `SQL_NULL`, `EMPTY_OR_SENTINEL`, `UNKNOWN`,
`NOT_APPLICABLE`, `INVALID_OR_UNRESOLVED` y `VALID`/`PRESENT`.
`PRESENT` no implica que un código sea correcto: algunos requieren diccionario.

Las referencias `_validation_run_id`, `_raw_ctid` y `_raw_hash` permiten auditar
el origen. `ctid` solo sirve dentro de esta instantánea y puede cambiar si se
reescribe raw; no es una clave permanente. MD5 es un identificador de comparación,
no una garantía criptográfica. Los candidatos de duplicación se informan sin
eliminar registros, y las claves lógicas exploratorias no prueban duplicación.

## Ejecución

Desde la raíz, con `.env` configurado:

```powershell
python -m analysis.run_clean_validation --plan
python -m analysis.check_validation_sql
python -m unittest discover -s tests -v
python -m analysis.run_clean_validation
```

Se puede limitar a una o varias fuentes:

```powershell
python -m analysis.run_clean_validation --sources edg enemdu
```

No se aceptan esquemas de destino arbitrarios. Cada ejecución utiliza nombres
nuevos y falla si existe su directorio de reporte; no borra ejecuciones previas.
No ejecutar en paralelo con cargas de las fuentes: se comparan controles antes
y después y un cambio externo hará que la ejecución requiera revisión.

ENEMDU se procesa por bloques de páginas dentro de una sola transacción con
instantánea estable; las expresiones repetidas se calculan una vez por bloque.
Si una ejecución falla, puede reanudarse sin repetir las fuentes confirmadas:

```powershell
python -m analysis.run_clean_validation --run-id IDENTIFICADOR_DE_EJECUCION --resume
```

Se conservan el manifiesto del fallo y la referencia inicial. Si se limitaron
las fuentes, deben indicarse las mismas opciones `--sources` al reanudar.

## Fechas de EDG

El parser general acepta ISO y año/mes/día explícito. Para fechas con año al
final, EDG utiliza además las columnas originales de día, mes y año: solo
recupera la fecha si coinciden con una interpretación válida del texto.
Las fechas imposibles o sin evidencia suficiente quedan pendientes.

Para refinar una ejecución ya completada con esta regla y regenerar sus
reportes sin reconstruir todo:

```powershell
python -m analysis.refine_validation --run-id IDENTIFICADOR_DE_EJECUCION
```

Esta operación solo actualiza fechas derivadas en su tabla EDG de validación.
Vuelve a comprobar los originales y los esquemas protegidos. Registra el código
del refinamiento y sus resultados en `refinamiento.json`.

## Resultados

En `reports/eda/<run_id>/`:

- `manifest.json`: versión del entorno, fuentes, destinos y estado.
- `protected_before.json`/`protected_after.json`: estructura, conteos, dos sumas
  de hashes de contenido y definición de vistas en esquemas protegidos.
- `conservacion.json`: resultado de la comparación; debe indicar `UNCHANGED`.
- Carpetas por fuente con perfiles de **todas las variables originales**,
  perfiles derivados, frecuencias, percentiles, cobertura mensual y por archivo,
  controles de coherencia, candidatos de duplicación y figuras agregadas.
- `cobertura_provincia_anio.json` y `cruces_candidatos.csv`: cobertura conjunta,
  sin construir cubos ni calcular asociaciones causales o estimaciones oficiales.
- `hallazgos.md`: resultados técnicos y pendientes de interpretación.

Resultado de la primera ejecución: [resultados del 16 de octubre de 2026](resultados_validacion_20261016.md).

Los perfiles no consideran 0/9/99/999 nulos universales; hay que revisar sus
diccionarios. Las reglas geográficas son controles iniciales, no una validación
administrativa o cartográfica definitiva. Los ingresos pueden incluir códigos
especiales aún no documentados. Los percentiles no autorizan su uso científico
sin revisar esas limitaciones y el diseño muestral.

Si las tablas operativas se llaman `*_limpia_1`, la comparación las detecta
como alternativa explícita y registra cuál consultó. Nunca las escribe.

## Punto de decisión posterior

Revisar diccionarios, hallazgos y cruces posibles con la investigadora. Aprobar
las reglas finales y los universos de análisis. Solo en una fase posterior
autorizada se evaluará publicar una versión operativa de clean y adaptar DW,
cubos, API o dashboard.
