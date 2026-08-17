import os
import glob
import pandas as pd
from sqlalchemy import text
from io import StringIO

from utils.config import engine

FOLDER = r"C:\Users\Administrador\Documents\Carolina\ArticuloCientífico\proyecto_ecuador_datos\data\enemdu"
TABLE = "enemdu"
CHUNKSIZE = 200_000

# ======================================================
# CSV robust reader
# ======================================================

def read_csv_robusto(path, chunksize=None):

    seps = [",", ";", "\t", "|"]
    encs = ["utf-8", "latin-1"]

    last_err = None

    for enc in encs:
        for sep in seps:
            try:
                return pd.read_csv(
                    path,
                    sep=sep,
                    encoding=enc,
                    chunksize=chunksize,
                    low_memory=False
                )
            except Exception as e:
                last_err = e

    raise last_err

# ======================================================
# COPY helper
# ======================================================

def psql_insert_copy(table, conn, keys, data_iter):

    dbapi_conn = conn.connection
    cursor = dbapi_conn.cursor()

    buffer = StringIO()
    pd.DataFrame(data_iter, columns=keys).to_csv(
        buffer,
        index=False,
        header=False
    )
    buffer.seek(0)

    cols = ",".join(keys)
    sql = f"COPY {table.name} ({cols}) FROM STDIN WITH CSV"

    cursor.copy_expert(sql, buffer)
    cursor.close()

# ======================================================
# 1️⃣ detectar TODAS columnas
# ======================================================

csv_files = glob.glob(os.path.join(FOLDER, "*.csv"))
print(f"Archivos encontrados: {len(csv_files)}")

all_columns = set()

for f in csv_files:

    df_head = next(read_csv_robusto(f, chunksize=1))
    cols = df_head.columns.str.strip().str.lower()
    all_columns.update(cols)

all_columns = sorted(all_columns)

print(f"Columnas totales detectadas: {len(all_columns)}")

# ======================================================
# 2️⃣ crear tabla vacía
# ======================================================

with engine.begin() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))

pd.DataFrame(columns=all_columns).to_sql(TABLE, engine, index=False)

# ======================================================
# 3️⃣ carga REAL
# ======================================================

for file in csv_files:

    print(f"\nProcesando {os.path.basename(file)}")

    for chunk in read_csv_robusto(file, chunksize=CHUNKSIZE):

        chunk.columns = chunk.columns.str.strip().str.lower()

        chunk = chunk.reindex(columns=all_columns)

        # FIX uint64
        for col in chunk.select_dtypes(include="uint64").columns:
            chunk[col] = chunk[col].astype("int64")

        chunk.to_sql(
            TABLE,
            engine,
            schema="raw",
            if_exists="append",
            index=False,
            method=psql_insert_copy
        )

print("\n✅ ENEMDU cargada completamente.")