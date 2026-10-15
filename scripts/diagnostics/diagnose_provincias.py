"""Diagnóstico: origen de espacios/homologación de provincias (solo lectura)."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import pandas as pd
from utils.config import engine


def q(sql):
    return pd.read_sql(sql, engine)


print("=" * 70)
print("1. Caracteres sobrantes en cubo_socioeconomico.provincia")
print("=" * 70)
df = q("SELECT DISTINCT provincia FROM dwh.cubo_socioeconomico ORDER BY provincia")
for v in df["provincia"]:
    tail = repr(v[len(v.rstrip()):]) if v != v.rstrip() else "-"
    print(f"  {v!r:40s} len={len(v):3d} tail={tail}")

print()
print("=" * 70)
print("2. ¿Qué tablas clean tienen provincia/canton con espacios colgantes?")
print("=" * 70)
tablas = q("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'clean'
      AND column_name IN ('provincia','canton','nombre_provincia','nombre_canton',
                          'prov_fall','cant_fall','prov_insc','cant_insc',
                          'prov_res','cant_res','ciudad')
    ORDER BY table_name, column_name
""")
for _, r in tablas.iterrows():
    t, c = r["table_name"], r["column_name"]
    try:
        res = q(f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN {c} <> TRIM({c}) THEN 1 ELSE 0 END) AS con_espacios
            FROM clean."{t}"
        """).iloc[0]
        if int(res["con_espacios"] or 0) > 0:
            print(f"  clean.{t}.{c}: {int(res['con_espacios']):,} de {int(res['total']):,}")
    except Exception as e:
        print(f"  clean.{t}.{c}: ERROR {e}")

print()
print("=" * 70)
print("3. Valores provincia por fuente (muestra con problemas)")
print("=" * 70)
fuentes = [
    ("homicidio_limpia", "provincia"),
    ("mdi_arma_limpia", "nombre_provincia"),
    ("mdi_desaparecido_limpia", "provincia"),
    ("edg_limpia", "prov_fall"),
    ("enemdu_limpia", "provincia"),
]
for t, c in fuentes:
    try:
        res = q(f"""
            SELECT DISTINCT {c} AS v FROM clean."{t}"
            WHERE {c} IS NOT NULL AND {c} <> TRIM({c})
            ORDER BY 1 LIMIT 5
        """)
        marca = "OK (sin espacios)" if res.empty else "CON ESPACIOS: " + ", ".join(
            repr(x) for x in res["v"].tolist()
        )
        print(f"  clean.{t}.{c}: {marca}")
    except Exception as e:
        print(f"  clean.{t}.{c}: {e}")

print()
print("=" * 70)
print("4. Compara nombres de provincia entre fuentes (normalizados)")
print("=" * 70)
sets = {}
for t, c in fuentes:
    try:
        r = q(f"SELECT DISTINCT {c} AS v FROM clean.\"{t}\" WHERE {c} IS NOT NULL")
        sets[f"{t}.{c}"] = set(str(x).strip().upper() for x in r["v"])
    except Exception:
        pass

base_key = "enemdu_limpia.provincia"
if base_key in sets:
    base = sets[base_key]
    print(f"  Base ({base_key}): {len(base)} valores")
    for k, s in sets.items():
        if k == base_key:
            continue
        solo_base = sorted(base - s)
        solo_otra = sorted(s - base)
        print(f"  vs {k}: solo_en_enemdu={solo_base}  solo_en_otra={solo_otra}")

print()
print("=" * 70)
print("5. dim_ubicacion: duplicados por provincia tras TRIM")
print("=" * 70)
print(q("""
    SELECT COUNT(*) AS filas,
           COUNT(DISTINCT provincia) AS provs_crudas,
           COUNT(DISTINCT TRIM(provincia)) AS provs_trim,
           COUNT(DISTINCT UPPER(TRIM(provincia))) AS provs_trim_upper
    FROM dwh.dim_ubicacion
""").to_string(index=False))

print()
print(q("""
    SELECT TRIM(provincia) AS provincia, COUNT(*) AS n
    FROM dwh.dim_ubicacion
    GROUP BY TRIM(provincia) ORDER BY n DESC LIMIT 30
""").to_string(index=False))
