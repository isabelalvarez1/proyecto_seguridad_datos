import pandas as pd
from utils.cleaning import clean_date_parts

PLACEHOLDERS = {
    "", " ", "  ", "\t",
    "na", "n/a", "n.a", "null", "none",
    "s/d", "sd", "sin dato", "sin datos",
    "-", "--", "---", ".", "..", "...",
    "nan"
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = pd.Index(df.columns).astype(str)

    cols_norm = (
        cols.str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.lower()
        .str.strip()
    )

    df = df.copy()
    df.columns = cols_norm

    if df.columns.duplicated().any():
        dup_cols = df.columns[df.columns.duplicated(keep=False)].tolist()
        print(f"⚠️ Columnas duplicadas detectadas: {dup_cols}")
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
        print(f"✅ Duplicadas resueltas. Total columnas: {len(df.columns)}")

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
    df = clean_date_parts(df)

    text_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()

    missing_values = {str(x).strip().upper() for x in PLACEHOLDERS}
    missing_values.update({
        "SIN INFORMACION",
        "SIN INFORMACIÓN",
        "SIN DATO",
        "SIN DATOS"
    })

    for col in text_cols:
        s = df[col].astype("string").str.strip().str.upper()
        s = s.replace(list(missing_values), pd.NA)

        if col in ["area", "area_fall", "area_res"]:
            s = s.replace({
                "URBANA": "URBANO",
                "URBANO": "URBANO",
                "RURAL": "RURAL",
            })

        df[col] = s.fillna("SIN_DATO")

    key_cols = infer_key_cols(df)
    if key_cols:
        print(f"🔑 Llave candidata detectada en EDG: {key_cols}")
    else:
        print("⚠️ No se pudo inferir llave candidata en EDG.")

    return df