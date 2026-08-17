import pandas as pd
from sqlalchemy import text

def load_data_chunks(engine, table: str, chunksize: int = 50000):
    sql = f"SELECT * FROM {table}"
    print(f"[load_data_chunks] SQL: {sql}")
    return pd.read_sql(sql, engine, chunksize=chunksize)

def save_to_postgres(
    df: pd.DataFrame,
    engine,
    schema: str,
    table: str,
    if_exists: str = "append",
    chunksize: int = 10000,
):
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        print(f"Columnas duplicadas detectadas: {duplicated}")
        df = df.loc[:, ~df.columns.duplicated()]

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    df.to_sql(
        name=table,
        con=engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
        method="multi",
        chunksize=chunksize,
    )