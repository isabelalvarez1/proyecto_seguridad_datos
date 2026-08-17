import re
import pandas as pd
from unidecode import unidecode

def normalize_colname(c: str) -> str:
    c = c.strip()
    c = unidecode(c)              # quita acentos
    c = c.lower()
    c = re.sub(r"\s+", "_", c)     # espacios -> _
    c = re.sub(r"[^a-z0-9_]", "", c)
    return c

def standardize_latlon_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1) normaliza todas las columnas (pero conserva originales mediante rename)
    norm_map = {c: normalize_colname(c) for c in df.columns}
    df = df.rename(columns=norm_map)

    # 2) candidatos típicos
    lat_candidates = ["latitud", "latitude", "lat", "y", "coordenada_y"]
    lon_candidates = ["longitud", "longitude", "lon", "lng", "x", "coordenada_x"]

    # 3) si no existe latitud pero hay un candidato, renombra
    if "latitud" not in df.columns:
        for c in lat_candidates:
            if c in df.columns:
                df = df.rename(columns={c: "latitud"})
                break

    if "longitud" not in df.columns:
        for c in lon_candidates:
            if c in df.columns:
                df = df.rename(columns={c: "longitud"})
                break

    return df