# Reportes locales

`eda/<run_id>/` contiene manifiesto, perfiles, frecuencias, controles,
figuras y hallazgos de una ejecución de `analysis/run_clean_validation.py`.

Las salidas se excluyen de Git. Los reportes son agregados y no exportan filas
individuales. Revisar cualquier resultado antes de compartirlo externamente.
Las referencias por fila permanecen en PostgreSQL, en clean_validacion.

`clean/<run_id>/` contiene los controles y resultados de construcción/publicación
de las tablas clean. Sus salidas también son locales y están excluidas de Git.

`analitica/<run_id>/` contiene matrices de selección, diccionarios de las vistas
y decisiones de imputación por campo. También se excluye de Git.

`investigacion/<run_id>/` contiene paneles agregados, exclusiones, protocolo,
predicciones temporales, métricas, figuras y modelos experimentales. No sustituye
los modelos de la API. Las salidas permanecen locales y excluidas de Git.
