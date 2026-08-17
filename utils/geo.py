import numpy as np
import pandas as pd
import unicodedata

# =========================================================
# Ecuador BBox (incluye Galápagos)
# =========================================================
ECU_LAT_MIN, ECU_LAT_MAX = -5.5,  2.5
ECU_LON_MIN, ECU_LON_MAX = -92.5, -74.0

# =========================================================
# Helpers numéricos y validación
# =========================================================
def to_num(s: pd.Series) -> pd.Series:
    """Convierte a numérico de forma robusta: soporta coma decimal y espacios."""
    s = s.astype("string").str.strip()
    s = s.str.replace(",", ".", regex=False)      # coma decimal -> punto
    s = s.str.replace(r"\s+", "", regex=True)     # quita espacios internos
    return pd.to_numeric(s, errors="coerce")

def in_world(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """Rango válido mundial."""
    return lat.between(-90, 90) & lon.between(-180, 180)

def in_ecuador(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """True si (lat,lon) cae dentro del bbox de Ecuador."""
    return lat.between(ECU_LAT_MIN, ECU_LAT_MAX) & lon.between(ECU_LON_MIN, ECU_LON_MAX)

# =========================================================
# Limpieza + Validación + Imputación GEO
# =========================================================
def clean_validate_impute_geo(
    df: pd.DataFrame,
    geo_pairs=None,
    admin_levels=("codigo_parroquia", "codigo_canton", "codigo_provincia"),
    min_support_by_level=None,
    force_provincia_fallback=True,
    use_national_fallback=True,
) -> pd.DataFrame:
    """
    - Limpia, corrige swap, valida, anula inválidos
    - Imputa por jerarquía (parroquia->canton->provincia)
    - Fallback provincia (opcional) y fallback nacional (opcional)
    """

    df = df.copy()

    if geo_pairs is None:
        geo_pairs = [
            ("latitud", "longitud", "geo"),
            ("latitud_desaparicion", "longitud_desaparicion", "geo_desaparicion"),
            ("latitud_localizacion", "longitud_localizacion", "geo_localizacion"),
        ]

    # soportes distintos por nivel (mejor práctica)
    if min_support_by_level is None:
        min_support_by_level = {
            "codigo_parroquia": 10,
            "codigo_canton": 5,
            "codigo_provincia": 3,
        }

    for lat_col, lon_col, pref in geo_pairs:
        if not {lat_col, lon_col}.issubset(df.columns):
            continue

        lat = to_num(df[lat_col])
        lon = to_num(df[lon_col])

        # 1) swap robusto:
        # - primero exige rango mundial para evitar swaps absurdos
        # - swap si al invertir cae en Ecuador y el original no
        ok_world = in_world(lat, lon)
        swap = ok_world & in_world(lon, lat) & in_ecuador(lon, lat) & (~in_ecuador(lat, lon))

        lat2 = lat.where(~swap, lon)
        lon2 = lon.where(~swap, lat)

        df[f"{lat_col}_num"] = lat2
        df[f"{lon_col}_num"] = lon2
        df[f"{pref}_swap_fixed"] = np.where(swap.fillna(False), 1, 0)

        # 2) validación (mundo + reglas + ecuador bbox)
        status = pd.Series("OK", index=df.index, dtype="string")
        error  = pd.Series("",   index=df.index, dtype="string")

        missing = lat2.isna() | lon2.isna()
        zero00  = (~missing) & (lat2.eq(0) & lon2.eq(0))
        out_wrld = (~missing) & (~zero00) & (~in_world(lat2, lon2))
        out_ec   = (~missing) & (~zero00) & (~out_wrld) & (~in_ecuador(lat2, lon2))

        status.loc[missing | zero00 | out_wrld | out_ec] = "ERROR"
        error.loc[missing]  = "missing_or_non_numeric"
        error.loc[zero00]   = "zero00"
        error.loc[out_wrld] = "out_world_range"
        error.loc[out_ec]   = "out_ecuador_bbox"

        df[f"{pref}_status"] = status
        df[f"{pref}_error"]  = error

        # 3) SOLO válidas originales (donantes)
        lat_clean = lat2.where(status.eq("OK"))
        lon_clean = lon2.where(status.eq("OK"))
        donors_mask = lat_clean.notna() & lon_clean.notna()

        # 4) inicial final
        lat_final = lat_clean.copy()
        lon_final = lon_clean.copy()
        imputed = pd.Series(0, index=df.index, dtype="int64")
        source_level = pd.Series("original", index=df.index, dtype="string")
        source_level.loc[lat_final.isna() | lon_final.isna()] = "none"

        # 5) imputación jerárquica
        for level in admin_levels:
            if level not in df.columns:
                continue

            min_sup = int(min_support_by_level.get(level, 5))

            stats = (
                df.loc[donors_mask, [level]]
                .assign(_lat=lat_clean[donors_mask].values, _lon=lon_clean[donors_mask].values)
                .groupby(level)[["_lat", "_lon"]]
                .agg(lat_med=("_lat", "median"),
                     lon_med=("_lon", "median"),
                     n=("_lat", "count"))
            )

            ok_groups = stats.index[stats["n"] >= min_sup]
            need = (lat_final.isna() | lon_final.isna()) & df[level].isin(ok_groups)

            lat_final.loc[need] = df.loc[need, level].map(stats["lat_med"])
            lon_final.loc[need] = df.loc[need, level].map(stats["lon_med"])
            imputed.loc[need] = 1
            source_level.loc[need] = level

        # 6) fallback provincia (sin min_support) si quieres reducir nulos más
        prov_col = "codigo_provincia"
        if force_provincia_fallback and prov_col in df.columns and donors_mask.any():
            stats_prov = (
                df.loc[donors_mask, [prov_col]]
                .assign(_lat=lat_clean[donors_mask].values, _lon=lon_clean[donors_mask].values)
                .groupby(prov_col)[["_lat", "_lon"]]
                .agg(lat_med=("_lat", "median"), lon_med=("_lon", "median"))
            )
            need_prov = (lat_final.isna() | lon_final.isna()) & df[prov_col].isin(stats_prov.index)
            lat_final.loc[need_prov] = df.loc[need_prov, prov_col].map(stats_prov["lat_med"])
            lon_final.loc[need_prov] = df.loc[need_prov, prov_col].map(stats_prov["lon_med"])
            imputed.loc[need_prov] = 1
            source_level.loc[need_prov] = "provincia_fallback"

        # 7) fallback nacional (opcional): elimina casi todos los nulos
        if use_national_fallback and donors_mask.any():
            need_nat = lat_final.isna() | lon_final.isna()
            if need_nat.any():
                lat_nat = lat_clean.median(skipna=True)
                lon_nat = lon_clean.median(skipna=True)
                lat_final.loc[need_nat] = lat_nat
                lon_final.loc[need_nat] = lon_nat
                imputed.loc[need_nat] = 1
                source_level.loc[need_nat] = "national_median"

        # 8) guardar
        df[f"{lat_col}_final"] = lat_final
        df[f"{lon_col}_final"] = lon_final
        df[f"{pref}_imputed"] = imputed
        df[f"{pref}_source_level"] = source_level
        df[f"{pref}_ok_final"] = np.where(lat_final.notna() & lon_final.notna(), 1, 0)

    return df