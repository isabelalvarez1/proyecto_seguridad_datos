import joblib
import pandas as pd
from utils.config import engine, DWH_SCHEMA

m = joblib.load('ml/modelos/mappings_homicidios.pkl')
print(f'Provincias en mapping: {len(m["provincia"])} | Cantones en mapping: {len(m["canton"])}')

df = pd.read_sql(f"""
    SELECT DISTINCT provincia, canton
    FROM {DWH_SCHEMA}.cubo_homicidio
    WHERE anio BETWEEN 2017 AND 2024
    ORDER BY provincia, canton
""", engine)

cantones_inv = {v: k for k, v in m['canton'].items()}
sin_mapeo = []
for _, row in df.iterrows():
    if row['canton'] not in cantones_inv:
        sin_mapeo.append(f"{row['provincia']} / {row['canton']}")

if sin_mapeo:
    print(f"\nCantones SIN mapping ({len(sin_mapeo)}):")
    for c in sin_mapeo:
        print(f"  - {c}")
else:
    print("\nTodos los cantones tienen mapping OK")

# Provincias en DB vs mapping
prov_inv = {v: k for k, v in m['provincia'].items()}
prov_db = df['provincia'].unique()
sin_prov = [p for p in prov_db if p not in prov_inv]
if sin_prov:
    print(f"\nProvincias SIN mapping: {sin_prov}")
