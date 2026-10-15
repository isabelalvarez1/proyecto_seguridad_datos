"""Prueba de humo geográfica: consulta el catálogo DPA sin escribir en la base."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import pandas as pd
from utils.cleaning import canonical_provincia, canonical_canton, normalize_geo_frame, fill_text_nulls
from utils.dwh_helpers import fill_key_nulls, dpa_lookup, dpa_from_codigos, normalizar_texto

casos = [
    "   CAÑAR", "GUAYAS", " LOJA ", " STO DGO DE LOS TSÁCHILAS",
    "SANTO DOMINGO  LOS TSÁCHILAS", "GALAPAGOS", "GALÁPAGOS",
    None, pd.NA, "", "SIN_DATO", "EXTERIOR", "ZONA NO DELIMITADA",
    "BENITO  JUAREZ",
]
print("canonical_provincia:")
for c in casos:
    print(f"  {c!r:42s} -> {canonical_provincia(c)!r}")

print("\ncanonical_canton:")
for c in ["  QUITO  ", "GUAYAQUIL", None, "  "]:
    print(f"  {c!r:42s} -> {canonical_canton(c)!r}")

print("\nDPA (dedupe + canónico):")
dpa = dpa_lookup()
print(dpa.head(3).to_string(index=False))
print(f"  filas={len(dpa)}  provincias={dpa['nombre_provincia'].nunique()}")
print("  2201 ->", dpa[dpa["codigo_canton"] == "2201"].to_dict("records"))
print("  con espacios en provincia:",
      int((dpa["nombre_provincia"] != dpa["nombre_provincia"].str.strip()).sum()))

print("\ndpa_from_codigos:")
s = pd.Series(["010101", "220150", "090150", "SIN_DATO", None])
print(dpa_from_codigos(s).to_string(index=False))

print("\nfill_key_nulls / normalize_geo_frame:")
df = pd.DataFrame({"provincia": ["   CAÑAR", None, "GALAPAGOS"], "canton": ["A ", None, "B"],
                   "valor": [1, 2, 3], "fecha": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])})
df = normalize_geo_frame(df, ["provincia", "canton"])
df = fill_key_nulls(df, ["provincia", "canton"])
print(df.to_string(index=False))
print("  'valor' intacto:", df["valor"].tolist(), "| fecha intacta:", str(df["fecha"].dtype))

print("\nnormalizar_texto con dtype string:")
d2 = pd.DataFrame({"a": pd.array(["  x  ", None, "nan"], dtype="string"), "b": [1.5, 2.5, 3.5]})
print(normalizar_texto(d2).to_string(index=False))

print("\nfill_text_nulls:")
print(fill_text_nulls(pd.DataFrame({"a": [None, "x"], "n": [1, 2]})).to_string(index=False))
print("\nOK")
