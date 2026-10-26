import pandas as pd
from utils.clean_fields import parse_source_dates
from utils.clean_projection import column_mapping

PLACEHOLDERS = {
    "", " ", "  ", "\t",
    "na", "n/a", "n.a", "null", "none",
    "s/d", "sd", "sin dato", "sin datos",
    "-", "--", "---", ".", "..", "...",
    "nan"
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.columns.duplicated().any():
        raise ValueError("Nombres exactamente duplicados: revisar el archivo de origen")
    df.columns = list(column_mapping(list(df.columns)).values())
    variants = [col for col in df.columns if col == "numeracion" or col.startswith("numeracion__")]
    if variants:
        df["numeracion_original"] = df[variants[0]]
        df["numeracion_conflicto"] = df[variants].nunique(axis=1, dropna=True).gt(1)
        df["numeracion"] = df[variants].bfill(axis=1).iloc[:, 0]
    return df


def infer_key_cols(df: pd.DataFrame):
    candidates = [
        ["id"],
        ["numeracion"],
        ["numero_acta"],
        ["nro_acta"],
        ["acta"],
        ["cod"],
    ]

    for cand in candidates:
        if all(c in df.columns for c in cand):
            return cand

    combo = ["prov_fall", "cant_fall", "parr_fall", "fecha_fall"]
    if all(c in df.columns for c in combo):
        return combo

    return None


def clean_edg(df: pd.DataFrame) -> pd.DataFrame:
    print("🧹 Limpieza personalizada EDG...")

    df = normalize_columns(df)
    for col in ["fecha_fall", "fecha_nac", "fecha_insc"]:
        if col in df.columns:
            if col + "_original" not in df.columns:
                df[col + "_original"] = df[col]
            suffix = col.removeprefix("fecha_")
            df[col] = parse_source_dates(df[col + "_original"], df.get("anio_" + suffix),
                                         df.get("mes_" + suffix), df.get("dia_" + suffix))

    text_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()

    missing_values = {str(x).strip().upper() for x in PLACEHOLDERS}
    missing_values.update({
        "SIN INFORMACION",
        "SIN INFORMACIÓN",
        "SIN DATO",
        "SIN DATOS"
    })

    for col in text_cols:
        if col.endswith("_original"):
            continue
        s = df[col].astype("string").str.strip().str.upper()
        s = s.replace(list(missing_values), pd.NA)

        if col in ["area", "area_fall", "area_res"]:
            s = s.replace({
                "URBANA": "URBANO",
                "URBANO": "URBANO",
                "RURAL": "RURAL",
            })

        # Mantener ausencias como nulos: los códigos desconocidos no se adivinan.
        df[col] = s
    if "edad" in df.columns:
        df["edad_original"] = df["edad"]
        df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
        if "cod_edad" in df.columns:
            df["edad_anios"] = df["edad"].where(df["cod_edad"].isin(["AÑOS", "A"]))

    key_cols = infer_key_cols(df)
    if key_cols:
        print(f"🔑 Llave candidata detectada en EDG: {key_cols}")
    else:
        print("⚠️ No se pudo inferir llave candidata en EDG.")

    return df
