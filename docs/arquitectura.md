# Arquitectura y mantenimiento

## Responsabilidades

- `scripts/load_raw.py`: lectura de archivos fuente a PostgreSQL.
- `utils/pipeline.py`: limpieza configurable por chunks.
- `scripts/clean_*.py`: reglas específicas por fuente.
- `scripts/create_dwh.py`: DDL de ocho dimensiones y cinco hechos; reconstruye
  tablas, no realiza una migración incremental de una base existente.
- `scripts/load_dimensiones.py` y `scripts/load_hechos.py`: cargas del DWH.
- `utils/cleaning.py`: normalización textual y geográfica compartida.
- `utils/dwh_helpers.py`: caché, catálogo DPA y uniones con dimensiones.
- `scripts/create_cubes.py`: definición y refresco de los seis cubos.
- `api/api_seguridad.py`: consultas agregadas y carga de modelos.
- `web/index.html`: interfaz estática actual.

Se conservan los nombres de los módulos operativos para mantener sus imports y
comandos. Los diagnósticos están en `scripts/diagnostics/`; el SQL antiguo se
archiva en `sql/archive/` y no define el despliegue vigente.

## Dependencias de datos

El DWH requiere las tablas:

```text
clean.homicidio_limpia
clean.mdi_arma_limpia
clean.mdi_desaparecido_limpia
clean.edg_limpia
clean.enemdu_limpia
catalogo.dpa_ecuador
```

El catálogo DPA debe contener al menos `codigo_canton`, `nombre_canton` y
`nombre_provincia`. Los códigos de cantón ausentes no se utilizan como claves
del catálogo para evitar que pandas asocie valores nulos entre sí. La selección
actual de códigos duplicados es determinista, pero requiere revisión semántica
contra un catálogo oficial para establecer correspondencias definitivas.

Las claves sustitutas se reconstruyen al ejecutar `todos`/`dims`: después de
recargar dimensiones deben recargarse los hechos y refrescarse los cubos.

## Cubos y dependencias

`cubo_seguridad_economia` agrega homicidios por provincia-año desde
`cubo_homicidio` y los une a ENEMDU agregada al mismo nivel. Por eso:

1. Se refresca homicidios antes que seguridad-economía.
2. En una eliminación deliberada, se elimina primero el cubo dependiente.
3. No se unen directamente las filas detalladas de homicidios y ENEMDU.

Las vistas `v_cubo_*` exponen los cubos materializados a Power BI. Una consulta
a la vista normal no desencadena un refresco de la materializada.

## API e interfaz

La API expone series anuales de homicidios, armas, desapariciones y defunciones;
ranking de provincias/cantones y predicciones. `/docs` enumera los contratos
vigentes. Todavía no hay endpoints que cubran todos los campos de los cubos.

Los modelos se cargan al importar la API desde `ml/modelos/`, usando rutas
relativas a la raíz del repositorio. Se necesita reiniciar el proceso después
de sustituir esos archivos.

El frontend actual consulta la API local y muestra un informe público Power BI.
La futura migración a Vue debe incorporar filtros coherentes, estados separados
de cero/sin dato/error y comprobaciones de totales en cada visualización.
