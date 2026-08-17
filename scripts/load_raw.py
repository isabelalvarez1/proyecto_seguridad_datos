import os
import glob
from pathlib import Path
from io import StringIO

import pandas as pd
from sqlalchemy import text
from utils.config import engine


# =========================================================
# Reader genérico de Excel
# =========================================================
def read_excel_robusto(path, sheet_name="1."):
    """Lee un archivo Excel intentando por nombre de hoja, luego por índice."""
    last_err = None
    try:
        return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except Exception as e:
        last_err = e
    try:
        return pd.read_excel(path, sheet_name=1, engine="openpyxl")
    except Exception as e:
        last_err = e
    raise RuntimeError(f"No pude leer {path}. Último error: {last_err}")


def load_raw_excel(folder, table_name, schema_name="raw", sheet_name="1."):
    """Carga todos los archivos Excel de una carpeta a una tabla PostgreSQL.

    Args:
        folder: ruta a la carpeta con archivos .xlsx/.xlsm/.xls
        table_name: nombre de la tabla destino
        schema_name: esquema destino (default: raw)
        sheet_name: nombre de la hoja a leer (default: "1.")
    """
    project_root = Path(__file__).resolve().parent.parent
    folder = str(project_root / folder) if not os.path.isabs(folder) else folder

    excel_files = sorted(
        glob.glob(os.path.join(folder, "*.xlsx")) +
        glob.glob(os.path.join(folder, "*.xlsm")) +
        glob.glob(os.path.join(folder, "*.xls"))
    )

    if not excel_files:
        raise FileNotFoundError(f"No se encontraron archivos Excel en: {folder}")

    dfs = []
    for f in excel_files:
        df = read_excel_robusto(f, sheet_name)
        df = df.dropna(axis=1, how="all")
        df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
        df["source_file"] = os.path.basename(f)
        dfs.append(df)
        print(f"OK: {os.path.basename(f)} -> cols={df.shape[1]} filas={df.shape[0]}")

    df_combined = pd.concat(dfs, ignore_index=True)
    all_cols = sorted(set().union(*[d.columns for d in dfs]))
    df_combined = df_combined.reindex(columns=all_cols)

    print(f"Filas totales: {len(df_combined)}")
    print(f"Columnas totales: {df_combined.shape[1]}")

    with engine.begin() as conn:
        info = conn.execute(text("""
            SELECT current_database() AS db, current_user AS usr
        """)).mappings().first()
        print(f"Conectado a: {dict(info)}")

        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        df_combined.to_sql(
            name=table_name,
            con=conn,
            schema=schema_name,
            if_exists="replace",
            index=False,
            chunksize=10000,
            method="multi"
        )

        exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :table
            );
        """), {"schema": schema_name, "table": table_name}).scalar()

        count = conn.execute(text(
            f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'
        )).scalar()

    print(f"Tabla creada: {exists} | Filas en {schema_name}.{table_name}: {count}")


# =========================================================
# Reader genérico de CSV
# =========================================================
def read_csv_robusto(path, chunksize=None):
    """Lee un CSV intentando múltiples separadores y encodings."""
    seps = [",", ";", "\t", "|"]
    encs = ["utf-8", "latin-1"]
    last_err = None

    for enc in encs:
        for sep in seps:
            try:
                return pd.read_csv(
                    path, sep=sep, encoding=enc,
                    chunksize=chunksize, low_memory=False
                )
            except Exception as e:
                last_err = e
    raise last_err


def load_raw_csv(folder, table_name, schema_name="raw", chunksize=200_000):
    """Carga todos los archivos CSV de una carpeta a una tabla PostgreSQL.

    Args:
        folder: ruta a la carpeta con archivos .csv
        table_name: nombre de la tabla destino
        schema_name: esquema destino (default: raw)
        chunksize: tamaño de chunk para lectura (default: 200k)
    """
    project_root = Path(__file__).resolve().parent.parent
    folder = str(project_root / folder) if not os.path.isabs(folder) else folder

    csv_files = sorted(glob.glob(os.path.join(folder, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No se encontraron CSV en: {folder}")

    # Detectar todas las columnas posibles
    all_columns = set()
    for f in csv_files:
        df_head = next(read_csv_robusto(f, chunksize=1))
        all_columns.update(df_head.columns.str.strip().str.lower())
    all_columns = sorted(all_columns)

    print(f"Archivos: {len(csv_files)} | Columnas totales: {len(all_columns)}")

    # Crear tabla vacía
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {schema_name}.{table_name}"))
    pd.DataFrame(columns=all_columns).to_sql(table_name, engine, schema=schema_name, index=False)

    # Carga real
    for f in csv_files:
        print(f"\nProcesando {os.path.basename(f)}")
        for chunk in read_csv_robusto(f, chunksize=chunksize):
            chunk.columns = chunk.columns.str.strip().str.lower()
            chunk = chunk.reindex(columns=all_columns)
            for col in chunk.select_dtypes(include="uint64").columns:
                chunk[col] = chunk[col].astype("int64")
            chunk.to_sql(
                table_name, engine, schema=schema_name,
                if_exists="append", index=False, chunksize=10000
            )

    print(f"\n{schema_name}.{table_name} cargada completamente.")


# =========================================================
# Punto de entrada directo
# =========================================================
if __name__ == "__main__":
    import sys

    loaders = {
        "homicidio": ("data/mdi_homicidio", "mdi_homicidio"),
        "arma":      ("data/mdi_arma", "mdi_arma"),
        "desaparecido": ("data/mdi_persona", "mdi_desaparecido"),
        "edg":       ("data/edg", "edg"),
        "enemdu":    ("data/enemdu", "enemdu"),
    }

    if len(sys.argv) < 2 or sys.argv[1] not in loaders:
        print(f"Uso: python load_raw.py <{'|'.join(loaders.keys())}>")
        sys.exit(1)

    name = sys.argv[1]
    folder, table = loaders[name]

    if name == "enemdu":
        load_raw_csv(folder, table)
    else:
        load_raw_excel(folder, table)