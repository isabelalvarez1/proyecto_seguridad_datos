import pandas as pd
from utils.clean_fields import normalize_period

REPLACEMENTS_TEXT = {
    "CIENT?FICOS": "CIENTÍFICOS",
    "P?BLICA": "PÚBLICA",
    "M?QUINAS": "MÁQUINAS",
    "T?CNICOS": "TÉCNICOS",
    "S?LO": "SÓLO",
    "ADMIN. P?BLICA": "ADMIN. PÚBLICA",
}

VARS_CODIGO_6 = [
    "ciudad",
    "p12b", "p15ab", "p17b",
    "ps08a", "ps09a", "ps10a",
    "pt01b", "pt08",
    "seg011", "seg0110", "seg012", "seg013", "seg014", "seg015",
    "seg016", "seg017", "seg018", "seg019",
    "seg091", "seg092", "seg093",
    "seg101", "seg102", "seg103", "seg104",
    "seg121", "seg122", "seg123"
]

VARS_CODIGO_4 = [
    "p40", "p41", "p52", "p53"
]

VARS_CATEGORICAS = [
    "informal", "formal",
    "p10b", "p16b", "p24", "p29", "p33", "p39",
    "p45", "p47b", "p51a",
    "p61a12", "p61a13", "p61a92",
    "p64b", "p68b",
    "p79a1", "p79a2", "p79b1", "p79b2",
    "pe02b", "pe05b", "pe06",
    "ps05a", "ps06a", "ps07a"
]

VARS_NUMERICAS = [
    "ingpc", "ingrl",
    "p63", "p65", "p66", "p67", "p69",
    "p71b", "p72b", "p73b", "p74b"
]


def fix_broken_text(value):
    if pd.isna(value):
        return value

    value = str(value)
    for bad, good in REPLACEMENTS_TEXT.items():
        value = value.replace(bad, good)

    return value


def limpiar_codigos(df, columnas, largo):
    for col in columnas:
        if col in df.columns:
            original = col + "_original"
            if original not in df.columns:
                df[original] = df[col]
            values = df[col].astype("string").str.strip()
            valid = values.str.fullmatch(r"\d{1," + str(largo) + r"}(?:\.0+)?", na=False)
            df[col] = values.where(valid).str.replace(r"\.0+$", "", regex=True).str.zfill(largo)
    return df


def limpiar_categoricas(df, columnas):
    for col in columnas:
        if col in df.columns:
            # No convertir etiquetas de encuesta en nulos por no ser números.
            df[col] = df[col].astype("string").str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
    return df


def limpiar_numericas(df, columnas):
    for col in columnas:
        if col in df.columns:
            if col + "_original" not in df.columns:
                df[col + "_original"] = df[col]
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clean_enemdu(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.lower().str.strip()
    for col in ["periodo", "p03", "ingpc", "ingrl", "fexp"]:
        if col in df.columns and col + "_original" not in df.columns:
            df[col + "_original"] = df[col]

    text_cols = df.select_dtypes(include=["object", "string"]).columns

    for col in text_cols:
        if col.endswith("_original"):
            continue
        df[col] = df[col].astype("string").str.strip().str.upper()
        df[col] = df[col].apply(fix_broken_text)

        if col == "area":
            df[col] = df[col].replace({
                "URBANA": "URBANO",
                "URBANO": "URBANO",
                "RURAL": "RURAL",
            })

    clean_cols = [col for col in df.columns if not col.endswith("_original")]
    df[clean_cols] = df[clean_cols].replace({
        "": pd.NA,
        "NAN": pd.NA,
        "NONE": pd.NA,
        "SIN_DATO": pd.NA
    })

    if "periodo" in df.columns:
        df["periodo"] = normalize_period(df["periodo_original"])
    if "p03" in df.columns:
        age = df["p03_original"].astype("string").str.strip().str.upper()
        df["p03"] = pd.to_numeric(age, errors="coerce")
        df["edad_censurada"] = age.isin(["98 Y MÁS", "98 Y MAS"])
        df["edad_limite_inferior"] = df["p03"].where(~df["edad_censurada"], 98)
    if "fexp" in df.columns:
        df["fexp"] = pd.to_numeric(df["fexp_original"], errors="coerce")
    df = limpiar_codigos(df, VARS_CODIGO_6, largo=6)
    df = limpiar_codigos(df, VARS_CODIGO_4, largo=4)
    df = limpiar_categoricas(df, VARS_CATEGORICAS)
    df = limpiar_numericas(df, VARS_NUMERICAS)

    return df
