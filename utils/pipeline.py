# utils/pipeline.py
import numpy as np
import pandas as pd
import time
from utils.geo_helpers import standardize_latlon_columns
from utils.geo import clean_validate_impute_geo
from utils.io_db import load_data_chunks, save_to_postgres
from utils.cleaning import (
    minimal_type_fix,
    clean_date_parts,
    expand_codigo_parroquia,
    limpiar_prov_canton_parroquia,
    full_clean_text_and_dedupe,
    fill_null_text_sin_dato,
    fix_all_datetime,
    fix_latlong_columns,
    normalize_genero,
)
from utils.calibre import clean_calibre

# ---------------------------------------------------------
# Reportes
# ---------------------------------------------------------
def report_nulls(df: pd.DataFrame, title: str, top: int = 10) -> None:
    null_pct = (df.isna().mean() * 100).round(2).sort_values(ascending=False)
    print(f"\n% nulos top {top} ({title}):")
    print(null_pct.head(top))


def report_sin_dato_filled(before: pd.DataFrame, after: pd.DataFrame) -> None:
    """Cuenta cuántos valores se llenaron a SIN_DATO por columna texto."""
    text_cols = after.select_dtypes(include=["object", "string", "category"]).columns
    if len(text_cols) == 0:
        return

    filled = {}
    for c in text_cols:
        b = before[c].isna()
        a = after[c].astype("string") == "SIN_DATO"
        filled[c] = int((b & a).sum())

    filled = {k: v for k, v in filled.items() if v > 0}
    if filled:
        print("\nValores rellenados con SIN_DATO (top):")
        for k, v in sorted(filled.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  {k}: {v}")


# ---------------------------------------------------------
# Hora a TIME (PostgreSQL)
# ---------------------------------------------------------
def convert_hora_to_time_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "hora_evento" not in df.columns:
        return df

    if str(df["hora_evento"].dtype).startswith("timedelta"):
        df["hora_evento"] = (pd.Timestamp("1970-01-01") + df["hora_evento"]).dt.time
    else:
        s = df["hora_evento"].astype("string").str.strip()
        df["hora_evento"] = pd.to_datetime(s, errors="coerce").dt.time

    return df
def run_pipeline(
    *,
    engine,
    table_in: str,
    schema_out: str,
    table_out: str,
    drop_cols=None,
    do_calibre: bool = True,
    do_geo: bool = True,   # <- nuevo
    custom_cleaner=None,
    read_chunksize: int = 50000,
    write_chunksize: int = 10000,
) -> None:
    t0 = time.time()
    print("[1] Inicio pipeline")

    total_rows = 0
    chunk_num = 0
    first_chunk = True

    for df in load_data_chunks(engine, table_in, chunksize=read_chunksize):
        chunk_num += 1
        t = time.time()

        print(f"\n[2] Chunk {chunk_num} cargado: {df.shape}")
        print(f"=== {table_in} -> {schema_out}.{table_out} ===")

        # -------------------------
        # 2) Type fix mínimo
        # -------------------------
        df2 = minimal_type_fix(df)
        df2 = clean_date_parts(df2)
        report_nulls(df2, f"chunk {chunk_num} post type-fix")

        # -------------------------
        # 3) Expand parroquia + limpiar nombres prov/cant/parr
        # -------------------------
        df3 = expand_codigo_parroquia(df2)
        df3 = limpiar_prov_canton_parroquia(df3)

        # -------------------------
        # 4) Clean texto + dedupe
        # -------------------------
        df4 = full_clean_text_and_dedupe(df3)
        print(f"[3] Chunk {chunk_num} después de clean+dedupe: {df4.shape}")
        df4 = normalize_genero(df4, "genero")
        # -------------------------
        # 5) GEO: estandarizar + validar + imputar
        # -------------------------
        print(f"[DEBUG] table_in={table_in} | do_geo={do_geo}")

        if do_geo:
            print(f"[DEBUG] GEO ACTIVADO para {table_in}")

            df4 = standardize_latlon_columns(df4)

            df5 = clean_validate_impute_geo(
                df4,
                admin_levels=("codigo_parroquia", "codigo_canton", "codigo_provincia"),
                min_support_by_level={
                    "codigo_parroquia": 10,
                    "codigo_canton": 5,
                    "codigo_provincia": 3,
                },
                force_provincia_fallback=True,
                use_national_fallback=False,
            )

            df5 = fix_latlong_columns(df5)
        else:
            print(f"[DEBUG] GEO DESACTIVADO para {table_in}")
            df5 = df4
        # -------------------------
        # 6) Fixes generales
        # -------------------------
        df5 = fix_all_datetime(df5)

        # -------------------------
        # 7) Calibre (opcional)
        # -------------------------
        if do_calibre:
            df5 = clean_calibre(df5)

        if custom_cleaner is not None:
            df5 = custom_cleaner(df5)

        report_nulls(df5, f"chunk {chunk_num} final antes de guardar")

        # -------------------------
        # 8) Preparar para SQL
        # -------------------------
        df5_sql = convert_hora_to_time_for_sql(df5)

        before_fill = df5_sql.copy()
        df5_sql = fill_null_text_sin_dato(df5_sql)
        report_sin_dato_filled(before_fill, df5_sql)

        if drop_cols:
            df5_sql = df5_sql.drop(columns=[c for c in drop_cols if c in df5_sql.columns])

        # -------------------------
        # 9) Save
        # -------------------------
        save_to_postgres(
            df5_sql,
            engine,
            schema_out,
            table_out,
            if_exists="replace" if first_chunk else "append",
            chunksize=write_chunksize,
        )

        first_chunk = False
        total_rows += len(df5_sql)

        print(f"[4] Chunk {chunk_num} guardado en {time.time() - t:.2f}s")
        print(f"[5] Filas acumuladas: {total_rows}")

    print(f"\n✅ Guardado OK: {schema_out}.{table_out}")
    print(f"✅ Pipeline completo en {time.time() - t0:.2f}s")