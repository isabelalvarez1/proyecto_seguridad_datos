import os
import glob
import pandas as pd
from sqlalchemy import text
from utils.config import engine

# ====== CONFIG ======
folder = r"C:\Users\Administrador\Documents\Carolina\ArticuloCientífico\proyecto_ecuador_datos\data\mdi_persona"
sheet_name = "1."          # hoja donde están los datos
schema_name = "raw"
table_name = "mdi_desaparecido"
# ====================

excel_files = sorted(
    glob.glob(os.path.join(folder, "*.xlsx")) +
    glob.glob(os.path.join(folder, "*.xlsm")) +
    glob.glob(os.path.join(folder, "*.xls"))
)

if not excel_files:
    raise FileNotFoundError(f"No se encontraron archivos Excel en: {folder}")

def read_excel_robusto(path, sheet):
    last_err = None

    # 1) Por nombre de hoja
    try:
        return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    except Exception as e:
        last_err = e

    # 2) Por índice (hoja 2 => índice 1)
    try:
        return pd.read_excel(path, sheet_name=1, engine="openpyxl")
    except Exception as e:
        last_err = e

    raise RuntimeError(f"No pude leer {path}. Último error: {last_err}")

dfs = []
for f in excel_files:
    df = read_excel_robusto(f, sheet_name)

    # Limpieza básica
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]

    df["source_file"] = os.path.basename(f)

    dfs.append(df)
    print(f"OK: {os.path.basename(f)} -> cols={df.shape[1]} filas={df.shape[0]}")

df_combined = pd.concat(dfs, ignore_index=True)

# Alinear columnas (por si difieren entre archivos)
all_cols = sorted(set().union(*[d.columns for d in dfs]))
df_combined = df_combined.reindex(columns=all_cols)

print("Filas totales:", len(df_combined))
print("Columnas totales:", df_combined.shape[1])

# ==========================
# CARGA + VERIFICACIÓN REAL
# ==========================
with engine.begin() as conn:
    # 1) Confirmar a qué DB/usuario/schema estás conectado
    info = conn.execute(text("""
        SELECT
          current_database()  AS db,
          current_user        AS usr,
          current_schema()    AS schema,
          inet_server_addr()  AS host,
          inet_server_port()  AS port;
    """)).mappings().first()
    print("📌 Conectado a:", dict(info))

    # 2) Asegurar que el esquema existe
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))

    # 3) Cargar (usando ESTA misma conexión)
    df_combined.to_sql(
        name=table_name,
        con=conn,                 # <- clave: usar la conexión del begin()
        schema=schema_name,
        if_exists="replace",
        index=False,
        chunksize=10000,
        method="multi"
    )

    # 4) Verificar existencia + conteo
    exists = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table
        );
    """), {"schema": schema_name, "table": table_name}).scalar()

    count = conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}";')).scalar()

print(f"✅ Tabla creada: {exists} | Filas en {schema_name}.{table_name}: {count}")