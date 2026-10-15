import pandas as pd
from sqlalchemy import text
from utils.config import engine
from utils.cleaning import (
    canonical_provincia,
    canonical_canton,
    collapse_ws,
)

# =========================================================
# Caché de dimensiones
# =========================================================
_DIM_CACHE: dict = {}

MESES_ES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo",
    "April": "Abril", "May": "Mayo", "June": "Junio",
    "July": "Julio", "August": "Agosto", "September": "Septiembre",
    "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}


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


def _is_text(s: pd.Series) -> bool:
    return (
        not pd.api.types.is_numeric_dtype(s)
        and not pd.api.types.is_datetime64_any_dtype(s)
        and not pd.api.types.is_bool_dtype(s)
    )


def fill_key_nulls(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Rellena nulos de texto en las claves de unión (evita filas sin match)."""
    df = df.copy()
    for c in cols:
        if c in df.columns and _is_text(df[c]):
            try:
                df[c] = df[c].fillna("SIN_DATO")
            except (TypeError, ValueError):
                df[c] = df[c].astype("string").fillna("SIN_DATO").astype(object)
    return df


def fill_dim_text(df: pd.DataFrame) -> pd.DataFrame:
    """Rellena nulos de TODAS las columnas de texto de una dimensión."""
    return fill_key_nulls(df, df.columns)


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

    der_cols = list(join_cols)
    izq_cols = list(left_cols) if left_cols is not None else der_cols

    # Mismo tratamiento de nulos en ambos lados -> mismo resultado que NULL==NULL
    sel = fill_key_nulls(sel, der_cols)
    h = fill_key_nulls(h, izq_cols)
    sel = sel.drop_duplicates(subset=der_cols)

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
    """Guarda una tabla de hechos en el esquema dwh (trunca antes de insertar)."""
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE dwh.{table} RESTART IDENTITY"))
        conn.commit()
    fact.to_sql(table, engine, schema="dwh", if_exists="append", index=False, chunksize=1000)
    print(f"{table} cargada: {len(fact):,} registros.")


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
    """Limpia columnas de texto: espacios colgantes, 'nan'/'None'/NA -> None.

    A diferencia de la versión anterior también cubre el dtype 'string' de pandas,
    que antes se escapaba al chequeo `dtype == "object"`.
    """
    for col in df.columns:
        if _is_text(df[col]):
            df[col] = df[col].map(collapse_ws)
    return df


# =========================================================
# Catálogo geográfico (DPA)
# =========================================================
def dpa_lookup() -> pd.DataFrame:
    """Catálogo DPA con nombres canónicos, un registro por código de cantón.

    El DPA local trae nombres con espacios iniciales y un código de cantón
    duplicado (2201) con dos nombres distintos: se deduplica de forma
    determinista (orden alfabético) para evitar que los joins dupliquen filas.
    """
    if "dpa" not in _DIM_CACHE:
        df = pd.read_sql(
            """
            SELECT DISTINCT ON (codigo_canton)
                   codigo_canton,
                   LEFT(codigo_canton, 2) AS codigo_provincia,
                   nombre_canton,
                   nombre_provincia
            FROM catalogo.dpa_ecuador
            WHERE codigo_canton IS NOT NULL
              AND codigo_canton <> ''
            ORDER BY codigo_canton, nombre_canton
            """,
            engine,
        )
        df["codigo_canton"] = df["codigo_canton"].astype("string").map(collapse_ws)
        df["codigo_provincia"] = df["codigo_provincia"].astype("string").map(collapse_ws)
        df["nombre_canton"] = df["nombre_canton"].map(canonical_canton)
        df["nombre_provincia"] = df["nombre_provincia"].map(canonical_provincia)
        _DIM_CACHE["dpa"] = df
    return _DIM_CACHE["dpa"]


def dpa_from_codigos(ciudad: pd.Series) -> pd.DataFrame:
    """Resuelve códigos ENEMDU (6 dígitos) a provincia/cantón canónicos."""
    cod = ciudad.astype("string").str.strip()
    cod4 = cod.str.extract(r"^(\d{4})", expand=False)
    dpa = dpa_lookup().rename(
        columns={
            "codigo_canton": "codigo_canton_join",
            "codigo_provincia": "codigo_provincia_join",
            "nombre_canton": "canton_join",
            "nombre_provincia": "provincia_join",
        }
    )
    out = pd.DataFrame({"codigo_canton_join": cod4})
    out = out.merge(dpa, on="codigo_canton_join", how="left")
    # Fallback al código de provincia solo cuando el código es un número válido
    provincia_respaldo = cod.where(cod.str.match(r"^\d{6}$")).str[:2].reset_index(drop=True)
    out["codigo_provincia_join"] = out["codigo_provincia_join"].fillna(provincia_respaldo)
    out.index = ciudad.index
    return out[["codigo_provincia_join", "provincia_join", "codigo_canton_join", "canton_join"]]


# =========================================================
# Utilidades de mantenimiento del DWH
# =========================================================
TABLAS_DWH = [
    "fact_homicidio", "fact_arma", "fact_desaparicion", "fact_defuncion", "fact_enemdu",
    "dim_tiempo", "dim_ubicacion", "dim_persona", "dim_geo_punto",
    "dim_arma", "dim_delito", "dim_motivacion", "dim_estado_caso",
]


def truncate_dwh() -> None:
    """Vacía hechos y dimensiones (los hechos dependen de las dimensiones por FK)."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(f"dwh.{t}" for t in TABLAS_DWH)
                + " RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()
    clear_dim_cache()
    print("dwh: hechos y dimensiones vaciados.")
