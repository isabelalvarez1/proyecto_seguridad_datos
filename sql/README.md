# SQL

`archive/` conserva consultas y definiciones históricas procedentes de
`scriptsSQL/`. Algunas contienen notas manuales y no son scripts ejecutables.

Las definiciones vigentes son:

- DDL dimensional: `scripts/create_dwh.py`.
- Cubos y vistas publicadas: `scripts/create_cubes.py`.

Para refrescar resultados utilizar `python -m scripts.run_pipeline cubos`.
No ejecutar los archivos históricos sobre una base actual para reemplazar cubos.
