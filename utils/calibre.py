import numpy as np
import pandas as pd
# =========================================================
# Limpieza ULTRA PRO del campo CALIBRE (CORREGIDA)
# =========================================================
def clean_calibre(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "calibre" not in df.columns:
        return df

    s = df["calibre"].astype("string").str.upper().str.strip()

    sin_dato_vals = [
        "SIN ESPECIFICAR", "SIN_DATO", "OTRO", "BALA U", "NA", "N/A", "-"
    ]
    s = s.replace(sin_dato_vals, "SIN_DATO")

    s = s.str.replace(r"\s+", "", regex=True)
    s = s.str.replace(r"\(.*?\)", "", regex=True)
    s = s.str.replace(r"^0+(\d)", r"\1", regex=True)

    df["calibre_clean"] = s

    df["calibre_num"] = (
        s.str.extract(r"(\d+)", expand=False)
         .astype("Float64")
    )

    mapa_calibres = {
        "9": "9MM LUGER",
        "9MM": "9MM LUGER",
        "9X19": "9MM LUGER",
        "223": ".223 REM",
        "556": "5.56 NATO",
        "556X45": "5.56 NATO",
        "308": "7.62 NATO",
        "762": "7.62 NATO",
        "762X39": "7.62 AK",
        "12": "12 GAUGE",
        "380": ".380 ACP",
        "357": ".357 MAGNUM",
        "44": ".44 MAGNUM",
        "40": ".40 S&W",
        "45": ".45 ACP",
        "22": ".22 LR",
        "177": ".177 AIR"
    }

    def map_estandar(val):
        if pd.isna(val):
            return "SIN_DATO"
        if val in mapa_calibres:
            return mapa_calibres[val]
        num = "".join([c for c in str(val) if c.isdigit()])
        return mapa_calibres.get(num, "SIN_DATO")

    df["calibre_estandarizado"] = df["calibre_clean"].apply(map_estandar)

    return df
