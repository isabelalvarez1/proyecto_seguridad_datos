import re

import pandas as pd
import numpy as np
from unidecode import unidecode
FALSE_NULLS = ["", " ", "  ", "NA", "N/A", "na", "n/a", "null", "NULL", "None", "none", "-", "--"]

# =========================================================
# Normalización geográfica (provincia / cantón)
# =========================================================
# Vocabulario canónico de provincias: clave sin tildes -> nombre mostrado con tildes.
PROVINCIAS_CANONICAS = {
    "AZUAY": "AZUAY",
    "BOLIVAR": "BOLÍVAR",
    "CARCHI": "CARCHI",
    "CANAR": "CAÑAR",
    "COTOPAXI": "COTOPAXI",
    "CHIMBORAZO": "CHIMBORAZO",
    "EL ORO": "EL ORO",
    "ESMERALDAS": "ESMERALDAS",
    "GUAYAS": "GUAYAS",
    "IMBABURA": "IMBABURA",
    "LOJA": "LOJA",
    "LOS RIOS": "LOS RÍOS",
    "MANABI": "MANABÍ",
    "MORONA SANTIAGO": "MORONA SANTIAGO",
    "NAPO": "NAPO",
    "ORELLANA": "ORELLANA",
    "PASTAZA": "PASTAZA",
    "PICHINCHA": "PICHINCHA",
    "SANTA ELENA": "SANTA ELENA",
    "SANTO DOMINGO DE LOS TSACHILAS": "SANTO DOMINGO DE LOS TSÁCHILAS",
    "SUCUMBIOS": "SUCUMBÍOS",
    "TUNGURAHUA": "TUNGURAHUA",
    "ZAMORA CHINCHIPE": "ZAMORA CHINCHIPE",
    "GALAPAGOS": "GALÁPAGOS",
    # Valores no provinciales que igual deben homologarse
    "ZONAS EN ESTUDIO": "ZONAS EN ESTUDIO",
    "ZONA NO DELIMITADA": "ZONA NO DELIMITADA",
    "EXTERIOR": "EXTERIOR",
    "SIN DATO": "SIN_DATO",
    "SIN_DATO": "SIN_DATO",
}

# Variantes reales encontradas en las fuentes (clave sin tildes) -> clave canónica.
PROVINCIAS_ALIASES = {
    "STO DGO DE LOS TSACHILAS": "SANTO DOMINGO DE LOS TSACHILAS",
    "STO DOMINGO DE LOS TSACHILAS": "SANTO DOMINGO DE LOS TSACHILAS",
    "SANTO DOMINGO LOS TSACHILAS": "SANTO DOMINGO DE LOS TSACHILAS",
    "SANTO DOMINGO TSACHILAS": "SANTO DOMINGO DE LOS TSACHILAS",
    "STO DGO LOS TSACHILAS": "SANTO DOMINGO DE LOS TSACHILAS",
    "D SANTO DOMINGO": "SANTO DOMINGO DE LOS TSACHILAS",
    "GALAPAGO": "GALAPAGOS",
    "GALAPAOS": "GALAPAGOS",
    "BOLIVAR ": "BOLIVAR",
}


def collapse_ws(s) -> str:
    """Colapsa espacios repetidos y recorta los extremos de un texto."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = str(s)
    if s.strip() == "" or s.strip().upper() in {"NAN", "NONE", "NULO", "<NA>"}:
        return None
    return re.sub(r"\s+", " ", s).strip()


def _geo_key(v):
    """Clave comparable: sin tildes, espacios simples, mayúsculas."""
    s = collapse_ws(v)
    if s is None:
        return None
    return re.sub(r"\s+", " ", unidecode(s)).strip().upper()


def canonical_provincia(v):
    """Devuelve el nombre canónico (con tildes) de una provincia."""
    k = _geo_key(v)
    if k is None:
        return None
    k = PROVINCIAS_ALIASES.get(k, k)
    return PROVINCIAS_CANONICAS.get(k, k)


def canonical_canton(v):
    """Colapsa espacios y homologa variantes conocidas del cantón."""
    canton = collapse_ws(v)
    if canton is not None and _geo_key(canton) == "DURAN":
        return "DURÁN"
    return canton


def normalize_geo_frame(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Aplica la normalización geográfica a las columnas indicadas."""
    df = df.copy()
    target = [c for c in (cols or df.columns) if c in df.columns]
    for c in target:
        if c == "provincia":
            df[c] = df[c].map(canonical_provincia)
        else:
            df[c] = df[c].map(canonical_canton)
    return df


def fill_text_nulls(df: pd.DataFrame, value: str = "SIN_DATO") -> pd.DataFrame:
    """Sustituye nulos de texto por un valor visible (evita claves nulas en Power BI)."""
    df = df.copy()
    text_cols = df.select_dtypes(include=["object", "string", "category"]).columns
    for c in text_cols:
        df[c] = df[c].astype("string").fillna(value)
        df[c] = df[c].astype(object)
    return df

def minimal_type_fix(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.replace(FALSE_NULLS, pd.NA)

    if "fecha_evento" in df.columns:
        df["fecha_evento"] = pd.to_datetime(df["fecha_evento"], errors="coerce")

    if "hora_evento" in df.columns:
        s = df["hora_evento"].astype("string").str.strip()
        df["hora_evento"] = pd.to_timedelta(s, errors="coerce")

    for c in ["latitud", "longitud"]:
        if c in df.columns:
            s = df[c].astype("string").str.strip().str.replace(",", ".", regex=False)
            df[c] = pd.to_numeric(s, errors="coerce")

    if "cantidad" in df.columns:
        s = df["cantidad"].astype("string").str.strip().str.replace(",", ".", regex=False)
        df["cantidad"] = pd.to_numeric(s, errors="coerce")

    codigo_cols = [c for c in df.columns if c.startswith("codigo_")]
    for c in codigo_cols:
        df[c] = df[c].astype("string")

    return df


def expand_codigo_parroquia(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "codigo_parroquia" not in df.columns:
        return df

    s = df["codigo_parroquia"].astype("string").str.strip()
    df["codigo_parroquia"] = s.str.split("-")
    df = df.explode("codigo_parroquia")
    df["codigo_parroquia"] = df["codigo_parroquia"].astype("string").str.strip()

    return df


def full_clean_text_and_dedupe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    text_cols = df.select_dtypes(include=["object", "string", "category"]).columns
    for c in text_cols:
        df[c] = df[c].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)

    if "latitud" in df.columns:
        df.loc[(df["latitud"] < -90) | (df["latitud"] > 90), "latitud"] = np.nan

    if "longitud" in df.columns:
        df.loc[(df["longitud"] < -180) | (df["longitud"] > 180), "longitud"] = np.nan

    before = len(df)
    df = df.drop_duplicates()
    print(f"Duplicados exactos eliminados: {before - len(df)}")

    possible_keys = [
        c for c in [
            "fecha_evento", "hora_evento", "lugar",
            "nombre_objeto", "clase_arma",
            "codigo_provincia", "codigo_canton", "codigo_distrito",
            "codigo_circuito", "codigo_subcircuito", "codigo_parroquia",
            "delito", "modalidad"
        ]
        if c in df.columns
    ]

    if len(possible_keys) >= 6:
        before2 = len(df)
        df = df.drop_duplicates(subset=possible_keys, keep="first")
        print(f"Duplicados lógicos eliminados: {before2 - len(df)}")
        print("Claves usadas:", possible_keys)

    return df


def limpiar_prov_canton_parroquia(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for c in ["codigo_provincia", "codigo_canton", "codigo_parroquia"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()

    if "codigo_provincia" in df.columns:
        prov = df["codigo_provincia"].str.extract(r"(\d+)", expand=False)
        df["codigo_provincia"] = prov.str.zfill(2)

    if "codigo_canton" in df.columns:
        raw = df["codigo_canton"].str.extract(r"(\d+)", expand=False)

        mask_4 = raw.str.len() == 4
        mask_3 = raw.str.len() == 3
        mask_1_2 = raw.str.len().isin([1, 2])

        df["codigo_canton"] = raw
        df.loc[mask_4, "codigo_canton"] = raw[mask_4]
        df.loc[mask_3, "codigo_canton"] = ("0" + raw)[mask_3]

        if "codigo_provincia" in df.columns:
            prov = df["codigo_provincia"]
            df.loc[mask_1_2, "codigo_canton"] = (prov + raw.str.zfill(2))[mask_1_2]
        else:
            df.loc[mask_1_2, "codigo_canton"] = raw.str.zfill(4)[mask_1_2]

        df["codigo_canton"] = df["codigo_canton"].astype("string").str.zfill(4)

    if "codigo_parroquia" in df.columns:
        p = df["codigo_parroquia"].str.extract(r"(\d+)", expand=False)

        mask_6 = p.str.len() == 6
        mask_5 = p.str.len() == 5
        mask_4 = p.str.len() == 4

        df["codigo_parroquia"] = p
        df.loc[mask_6, "codigo_parroquia"] = p[mask_6]
        df.loc[mask_5, "codigo_parroquia"] = ("0" + p)[mask_5]

        if "codigo_provincia" in df.columns:
            prov = df["codigo_provincia"]
            df.loc[mask_4, "codigo_parroquia"] = (prov + p.str.zfill(4))[mask_4]
        else:
            df.loc[mask_4, "codigo_parroquia"] = p.str.zfill(6)[mask_4]

        df["codigo_parroquia"] = df["codigo_parroquia"].astype("string").str.zfill(6)

    return df


def fill_null_text_sin_dato(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    text_cols = df.select_dtypes(include=["object", "string", "category"]).columns
    df[text_cols] = df[text_cols].fillna("SIN_DATO")
    return df


def fix_all_datetime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    date_cols = [c for c in df.columns if c.startswith("fecha_")]
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    return df


def fix_latlong_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    geo_cols = [c for c in df.columns if c.startswith(("latitud", "longitud"))]
    for c in geo_cols:
        s = df[c].astype("string").str.strip().str.replace(",", ".", regex=False)
        df[c] = pd.to_numeric(s, errors="coerce")

    return df


_MOJIBAKE_MAP = {
    "ESPAÃ‘A": "ESPAÑA",
    "ESPAÃ\u0091A": "ESPAÑA",
    "ESPAÃ?A": "ESPAÑA",
    "ESPA?A": "ESPAÑA",
}


def _normalize_unicode_text(s: pd.Series) -> pd.Series:
    s = s.astype("string")
    s = s.str.normalize("NFKC")
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return s


def clean_nacionalidad(
    s: pd.Series,
    *,
    unknown_value: str = "SIN_DATO",
    to_upper: bool = True,
) -> pd.Series:
    s = _normalize_unicode_text(s)
    s = s.replace(_MOJIBAKE_MAP)

    if to_upper:
        s = s.str.upper()

    s = s.replace({"": pd.NA, "NAN": pd.NA, "NONE": pd.NA})
    s = s.fillna(unknown_value)

    return s


def clean_int_column(
    df: pd.DataFrame,
    col: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> pd.DataFrame:
    df = df.copy()

    if col not in df.columns:
        return df

    df[col] = pd.to_numeric(df[col], errors="coerce")

    if min_value is not None:
        df.loc[df[col] < min_value, col] = np.nan

    if max_value is not None:
        df.loc[df[col] > max_value, col] = np.nan

    df[col] = df[col].astype("Int64")
    return df

def clean_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Normalizar nombres de columnas primero
    df.columns = df.columns.str.strip().str.lower()

    # Limpiar días
    for col in ["dia_nac", "dia_fall", "dia_insc"]:
        if col in df.columns:
            df = clean_int_column(df, col, 1, 31)

    # Limpiar años
    for col in ["anio_nac", "anio_insc"]:
        if col in df.columns:
            df = clean_int_column(df, col, 1900, 2025)

    # Limpiar y normalizar edad si existe
    if "edad" in df.columns:
        df = clean_int_column(df, "edad", 0, 120)
    return df

def normalize_text_missing(
    df: pd.DataFrame,
    *,
    replacement: str = "SIN_DATO",
    extra_missing=None
) -> pd.DataFrame:
    df = df.copy()

    if extra_missing is None:
        extra_missing = set()

    missing_values = {
        "", " ", "  ", "\t",
        "NA", "N/A", "N.A", "NULL", "NONE",
        "S/D", "SD", "SIN DATO", "SIN DATOS",
        "SIN INFORMACION", "SIN INFORMACIÓN",
        "-", "--", "---", ".", "..", "...",
        "NAN"
    }

    missing_values.update({str(x).strip().upper() for x in extra_missing})

    text_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()

    for col in text_cols:
        s = df[col].astype("string").str.strip().str.upper()
        s = s.replace(list(missing_values), pd.NA)
        df[col] = s.fillna(replacement)

    return df

def normalize_genero(df: pd.DataFrame, col: str = "genero") -> pd.DataFrame:
    df = df.copy()

    if col not in df.columns:
        return df

    s = df[col].astype("string").str.strip().str.upper()
    s = s.apply(lambda x: unidecode(x) if pd.notna(x) else x)

    mapping = {
        "FEMENINO": "FEMENINO",
        "MASCULINO": "MASCULINO",

        "TRANS": "TRANS",
        "TRANSEXUAL": "TRANS",
        "TRANSGENERO": "TRANS",
        "TRANSGENERO FEMENINC": "TRANS FEMENINO",
        "TRANSGENERO FEMENINO": "TRANS FEMENINO",
        "TRANS FEME": "TRANS FEMENINO",
        "TRANS FEM": "TRANS FEMENINO",

        "TRANSGENERO MASCULIN": "TRANS MASCULINO",
        "TRANSGENERO MASCULINO": "TRANS MASCULINO",
        "TRANS MASC": "TRANS MASCULINO",
        "TRANS MASCULINO": "TRANS MASCULINO",

        "NO APLICA": "NO APLICA",
        "SIN DATO": "SIN DATO",
    }

    s = s.replace(mapping)

    # valores no mapeados, opcional
    s = s.fillna("SIN DATO")

    df[col] = s
    return df
