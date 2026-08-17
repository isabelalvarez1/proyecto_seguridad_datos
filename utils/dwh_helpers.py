import pandas as pd
from utils.config import engine

# =========================================================
# Caché de dimensiones
# =========================================================
_DIM_CACHE: dict = {}


def get_dim(name: str) -> pd.DataFrame:
    """Carga una dimensión desde el DWH y la guarda en caché (una sola vez)."""
    if name not in _DIM_CACHE:
        _DIM_CACHE[name] = pd.read_sql(f"SELECT * FROM dwh.{name}", engine)
    return _DIM_CACHE[name]


def clear_dim_cache() -> None:
    """Limpia la caché de dimensiones."""
    _DIM_CACHE.clear()


# =========================================================
# Helpers de merge
# =========================================================
def merge_tiempo(h: pd.DataFrame, fecha_col: str) -> pd.DataFrame:
    """Merge con dim_tiempo usando una única columna de fecha."""
    dim = get_dim("dim_tiempo").copy()
    dim["fecha"] = pd.to_datetime(dim["fecha"]).dt.date
    h[fecha_col] = pd.to_datetime(h[fecha_col], errors="coerce").dt.date
    return h.merge(
        dim[["tiempo_key", "fecha"]].drop_duplicates(subset=["fecha"]),
        left_on=fecha_col,
        right_on="fecha",
        how="left",
    )


def merge_tiempo_multi(h: pd.DataFrame, fecha_map: dict) -> pd.DataFrame:
    """Merge con dim_tiempo usando varias columnas de fecha.

    fecha_map: dict {columna_fecha: nombre_key_resultante}
    """
    dim = get_dim("dim_tiempo").copy()
    dim["fecha"] = pd.to_datetime(dim["fecha"]).dt.date
    dt_dedup = dim[["tiempo_key", "fecha"]].drop_duplicates(subset=["fecha"])

    for col_fecha, key_name in fecha_map.items():
        if col_fecha in h.columns:
            h[col_fecha] = pd.to_datetime(h[col_fecha], errors="coerce").dt.date
            h = h.merge(
                dt_dedup.rename(columns={"tiempo_key": key_name}),
                left_on=col_fecha,
                right_on="fecha",
                how="left",
            )
            if "fecha" in h.columns:
                h.drop(columns=["fecha"], inplace=True)
    return h


def merge_dim(
    h: pd.DataFrame,
    dim_name: str,
    join_cols,
    select_cols=None,
    left_cols=None,
) -> pd.DataFrame:
    """Merge genérico con una dimensión del DWH.

    join_cols: columnas usadas para el join (lado derecho).
    select_cols: columnas a tomar de la dimensión (None = todas).
    left_cols: si se especifica, se usa como left_on (join con nombres distintos).
    """
    dim = get_dim(dim_name)
    sel = dim if select_cols is None else dim[select_cols]
    sel = sel.drop_duplicates(subset=join_cols)

    if left_cols is not None:
        return h.merge(sel, left_on=left_cols, right_on=join_cols, how="left")
    return h.merge(sel, on=join_cols, how="left")


def merge_geo(h: pd.DataFrame) -> pd.DataFrame:
    """Merge con dim_geo_punto usando latitud_final/longitud_final."""
    dim = get_dim("dim_geo_punto")
    cols = ["latitud", "longitud", "geo_status", "geo_error", "geo_source_level", "geo_ok_final"]
    return h.merge(
        dim.drop_duplicates(subset=cols),
        left_on=["latitud_final", "longitud_final"] + cols[2:],
        right_on=cols,
        how="left",
    )


# =========================================================
# Helpers de guardado
# =========================================================
def ensure_cols(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Agrega columnas faltantes con None."""
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df


def save_fact(fact: pd.DataFrame, table: str) -> None:
    """Guarda una tabla de hechos en el esquema dwh."""
    fact.to_sql(table, engine, schema="dwh", if_exists="append", index=False, chunksize=1000)
    print(f"{table} cargada.")


# =========================================================
# Helpers de transformación
# =========================================================
def rango_edad(edad):
    if pd.isna(edad):
        return None

    try:
        edad = int(edad)
    except Exception:
        return None

    if edad < 12:
        return "0-11"
    elif edad < 18:
        return "12-17"
    elif edad < 30:
        return "18-29"
    elif edad < 45:
        return "30-44"
    elif edad < 65:
        return "45-64"
    else:
        return "65+"


def normalizar_texto(df):
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": None, "nan": None, "None": None})
    return df