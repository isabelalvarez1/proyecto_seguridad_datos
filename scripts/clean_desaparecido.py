import pandas as pd
from utils.cleaning import clean_nacionalidad
from utils.cleaning import normalize_text_missing
def clean_desaparecido(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # limpieza genérica texto
    df = normalize_text_missing(df)
    # Normalizar sexo
    if "sexo" in df.columns:
        s = df["sexo"].astype("string").str.upper().str.strip()
        s = s.replace({
            "MASCULINO": "M",
            "FEMENINO": "F",
            "HOMBRE": "M",
            "MUJER": "F",
        })
        # valores raros a SIN_DATO
        s = s.where(s.isin(["M", "F"]), "SIN_DATO")
        df["sexo"] = s

    # Edad a numérico si existe
    if "edad" in df.columns:
        df["edad"] = pd.to_numeric(df["edad"].astype("string").str.extract(r"(\d+)", expand=False), errors="coerce")

    # Opcional: crear rango_edad si no existe
    if "edad" in df.columns and "rango_edad" not in df.columns:
        bins = [-1, 5, 12, 17, 29, 44, 59, 200]
        labels = ["0-5", "6-12", "13-17", "18-29", "30-44", "45-59", "60+"]
        df["rango_edad"] = pd.cut(df["edad"], bins=bins, labels=labels).astype("string")
# Nacionalidad (genérica)
    if "nacionalidad" in df.columns:
        df["nacionalidad"] = clean_nacionalidad(df["nacionalidad"])
    return df