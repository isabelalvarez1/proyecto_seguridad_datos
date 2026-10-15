# Datos locales

Los archivos de datos se conservan localmente y se excluyen de Git. Las rutas
esperadas por `scripts/load_raw.py` son:

| Carpeta | Fuente / tabla raw |
|---|---|
| `data/mdi_homicidio/` | Homicidios / `raw.mdi_homicidio` |
| `data/mdi_arma/` | Armas / `raw.mdi_arma` |
| `data/mdi_persona/` | Desapariciones / `raw.mdi_desaparecido` |
| `data/edg/` | Defunciones / `raw.edg` |
| `data/enemdu/` | Encuesta ENEMDU / `raw.enemdu` |
| `data/staging_unificados/` | Salidas locales de preparación anteriores |

Crear las carpetas necesarias y colocar los archivos antes de ejecutar la
carga. ENEMDU se lee como CSV; las otras fuentes usan Excel. Revisar las hojas
esperadas por el lector antes de sustituir un conjunto de archivos.

Registrar origen, fecha, diccionario y cobertura de cada descarga. El catálogo
`catalogo.dpa_ecuador` debe provisionarse aparte: no hay una descarga automática
del catálogo en este repositorio.
