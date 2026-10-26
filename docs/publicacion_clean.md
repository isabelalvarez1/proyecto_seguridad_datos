# Construcción y publicación de clean

## Alcance

`scripts/run_clean.py` publica las cinco fuentes después de una ejecución de
validación completada. No ejecuta `run_pipeline`, no carga el DW, no refresca
cubos y no modifica API, modelos o dashboard.

La selección de variables para cruces y el diseño posterior del DW son una fase
separada. Los resultados de los cubos actuales siguen correspondiendo a su carga
anterior, aunque haya una versión nueva de clean.

## Flujo reproducible

1. Preparar las fuentes y registrar su procedencia en `raw`.
2. Ejecutar `python -m analysis.run_clean_validation` y revisar los hallazgos.
3. Aprobar las reglas y los tratamientos pendientes antes de publicar.
4. Construir tablas nuevas en `clean_preparacion` y comprobar contenido original,
   filas, períodos/fechas y conservación de esquemas ajenos.
5. Publicar las cinco tablas juntas en una transacción.

Ejemplo para la validación revisada:

```powershell
python -m scripts.run_clean --validation-run validacion_20261016_01 --plan
python -m scripts.run_clean --validation-run validacion_20261016_01 --publish
```

Sin `--publish`, el comando deja las salidas comprobadas en `clean_preparacion`.
Tras una publicación correcta y sus controles, elimina automáticamente
`clean_preparacion` si está vacío. Utiliza `DROP SCHEMA ... RESTRICT`, sin
`CASCADE`: si contiene objetos pendientes, los conserva y registra
`KEPT_NOT_EMPTY` en el manifiesto. Si la carga falla o no se solicita publicar,
no ejecuta esa limpieza. El esquema se crea otra vez cuando una nueva carga
lo necesita.
Cada ejecución utiliza un identificador nuevo; no sobrescribe sus reportes.
Si se interrumpe, revisar el manifiesto y el estado de las tablas antes de
relanzar. El publicador no ofrece aún reanudación automática de una carga parcial.

## Tablas publicadas

```text
clean.homicidio_limpia
clean.mdi_arma_limpia
clean.mdi_desaparecido_limpia
clean.edg_limpia
clean.enemdu_limpia
```

Las tablas existentes con sufijo `_1` se conservan con el mismo nombre. Cuando
ya existe una tabla con el nombre canónico, la siguiente publicación la mueve
a `clean_historial` con sufijo de ejecución, sin eliminarla. Las vistas normales
administradas de `analitica` se reenlazan al nuevo objeto dentro de la misma
transacción conservando sus OID. Ante dependencias ajenas al contrato o cambios
incompatibles, la publicación se detiene y revierte.

La publicación utiliza bloqueo de tablas y un bloqueo asesor transaccional.
Los lectores ven la versión anterior o el conjunto nuevo una vez confirmado;
no se publica una mezcla de fuentes parcialmente cargadas.

## Contrato de columnas

- Nombres en minúsculas y sin tildes; si hay colisiones se mantienen variantes
  numeradas (`numeracion__2`, `numeracion__3`), no se descartan.
- Variables transformadas con `*_original`: permiten reconstruir el registro raw.
- `*_estado`: diferencia nulo, desconocido, no aplicable, conversión válida y
  respuesta pendiente. Una categoría presente no garantiza su validez semántica.
- `_clean_run_id`, `_validation_run_id`, `_raw_hash`, `_raw_ctid`: procedencia.
  CTID sirve como referencia de la instantánea, no como identificador permanente.
- Nulos SQL reales para ausencias; no se introduce `SIN_DATO` en números o fechas.
- No se eliminan registros ni candidatos de duplicación automáticamente.

### ENEMDU

- `periodo`: texto `YYYYMM`, conservando `periodo_original` y `periodo_estado`.
- `fexp`, `ingpc`, `ingrl`, `p03`: números cuando hay valor exacto interpretable.
- `edad_censurada` y `edad_limite_inferior`: conservan «98 y más» como categoría
  abierta. `p03`/`edad_anios` permanecen nulos en esos casos, no se fijan a 98.
- `ingrl_respuesta` conserva respuestas como «Gasta mas de lo que gana»;
  `ingrl_estado` distingue respuesta no numérica de «No informa».
- `sector`, `secemp`, `rama1`, `condact` y `condactn` no se mezclan sin diccionario.
- Nombres DPA solo con correspondencia única; ambiguos/no encontrados quedan
  explícitos en `dpa_estado` y sus nombres no se inventan.

### Defunciones

- Fechas confirmadas con los componentes originales cuando el formato es ambiguo.
- Edad y unidad se conservan; `edad_anios` no confunde horas/días/meses con años.
- `fecha_nac_posterior_fall` marca incoherencias sin eliminar el registro.
- Variantes de numeración coalescidas con originales y señal de conflicto.
- Códigos de autopsia o causa no se convierten a sí/no sin diccionario.

### Geografía y coordenadas

- Se aplican variantes territoriales ya verificadas, como Durán.
- Pares (0,0), incompletos o fuera de rango global quedan nulos en coordenadas
  limpias; se conserva el original y un `geo_*_estado` que explica el motivo.
- No hay imputación de coordenadas, sustitución por centroides ni intercambio
  automático de latitud/longitud. Estar dentro del rango global no valida la
  ubicación exacta ni demuestra pertenencia a un cantón.

## Código y verificación

- `utils/validation_sql.py`: conversiones SQL compartidas con el análisis.
- `utils/clean_projection.py`: contrato y trazabilidad de la publicación.
- `utils/clean_fields.py`: conversiones pandas conservadoras.
- `scripts/clean_enemdu.py` y `scripts/clean_edg.py`: limpiadores corregidos para
  uso independiente. El flujo aprobado para publicar todas las fuentes es
  `scripts/run_clean.py`, no una ejecución genérica de los cargadores antiguos.

```powershell
python -m unittest discover -s tests -v
python -m analysis.check_validation_sql
python -m analysis.check_clean_sql
```

El último ensayo usa muestras de la validación `validacion_20261016_01` en
solo lectura. Los ensayos SQL no publican tablas ni recargan esquemas.

## Reportes

En `reports/clean/<run_id>/` se guardan:

- `manifest.json`: estado, tablas y huellas del código utilizado.
- `protected_before.json` y `protected_after_build.json`: controles de contenido,
  estructura y vistas antes y después de construir, antes del intercambio final.
- `conservacion.json`: resultado y comprobación de identidad de objetos previos
  después de publicar; no es un hash nuevo del contenido posterior al intercambio.
- Por fuente: mapeo de columnas, estados, cobertura anual y controles de originales.
- `resultado.md`: resumen de resultados y pendientes.

Las salidas son locales y están excluidas de Git. No se exportan filas de personas.

Primera publicación completada: [resultados del 18 de octubre de 2026](resultados_clean_20261018.md).

Para comprobar las métricas de las tablas ya publicadas y repetir los controles
de contenido de raw, DW y catálogo después del intercambio:

```powershell
python -m analysis.check_published_clean --run-id IDENTIFICADOR_DE_PUBLICACION
```

El resultado se guarda en `postpublication_audit.json`. El comando solo consulta
PostgreSQL; no recarga ni refresca ningún objeto.
