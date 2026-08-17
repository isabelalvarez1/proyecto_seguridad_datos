#si vale
import os
import glob
import pandas as pd
from utils.config import engine

# ====== CONFIG ======
folder = r"C:\Users\Administrador\Documents\Carolina\ArticuloCientífico\proyecto_ecuador_datos\data\edg"

# Cambia estos datos según tu Postgres

#schema_name = "public"
#table_name = "edg"   # se creará como public.edg
# ====================

csv_files = sorted(glob.glob(os.path.join(folder, "*.csv")))
if not csv_files:
    raise FileNotFoundError(f"No se encontraron CSV en: {folder}")

def read_csv_robusto(path):
    seps = [",", ";", "\t", "|"]
    encs = ["utf-8", "latin-1"]
    last_err = None

    for enc in encs:
        for sep in seps:
            # engine C
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, engine="c", low_memory=False)
                if df.shape[1] == 1:
                    continue
                return df
            except Exception as e:
                last_err = e

            # engine python (sin low_memory)
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, engine="python", on_bad_lines="skip")
                if df.shape[1] == 1:
                    continue
                return df
            except Exception as e:
                last_err = e

    raise RuntimeError(f"No pude leer {path}. Último error: {last_err}")

dfs = []
for f in csv_files:
    df = read_csv_robusto(f)

    # (opcional) agrega columna de origen
    df["source_file"] = os.path.basename(f)

    dfs.append(df)
    print(f"OK: {os.path.basename(f)} -> cols={df.shape[1]} filas={df.shape[0]}")

# Unir
df_combined = pd.concat(dfs, ignore_index=True)

# IMPORTANTE: alinear columnas (por tus 45 vs 46 columnas)
# Esto rellena con NaN las columnas faltantes en algunos años.
all_cols = sorted(set().union(*[d.columns for d in dfs]))
df_combined = df_combined.reindex(columns=all_cols)

print("Filas totales:", len(df_combined))
print("Columnas totales:", df_combined.shape[1])


df_combined.to_sql(
    name="edg",          # nombre de la tabla
    con=engine,
    schema="raw",    # esquema
    if_exists="replace",
    index=False,
    chunksize=10000,
    method="multi"
)

print("✅ Cargado en PostgreSQL: public.edg")