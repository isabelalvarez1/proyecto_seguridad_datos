import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import pandas as pd
import joblib
from utils.config import engine, DWH_SCHEMA, PROJECT_ROOT
from utils.cleaning import canonical_provincia

app = FastAPI(
    title="API Seguridad Pública Ecuador",
    description="API para consultar datos y predicciones de seguridad pública",
    version="2.0.0"
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Cargar modelos + mappings ─────────────────────────────
MODEL_DIR = PROJECT_ROOT / 'ml' / 'modelos'
rf_homicidios  = joblib.load(MODEL_DIR / 'rf_homicidios.pkl')
xgb_homicidios = joblib.load(MODEL_DIR / 'xgb_homicidios.pkl')
rf_riesgo      = joblib.load(MODEL_DIR / 'rf_clasificador_riesgo.pkl')
mappings_hom   = joblib.load(MODEL_DIR / 'mappings_homicidios.pkl')
feature_cols   = joblib.load(MODEL_DIR / 'features_homicidios.pkl')
mappings_riesgo = joblib.load(MODEL_DIR / 'mappings_riesgo.pkl')

hom_prov_inv = {v: k for k, v in mappings_hom['provincia'].items()}
riesgo_prov_inv = {v: k for k, v in mappings_riesgo['provincia'].items()}
riesgo_canton_inv = {v: k for k, v in mappings_riesgo['canton'].items()}


# ── Helper: calcular features temporales para prediccion ──
def calcular_features_provincia(provincia: str, anio: int, mes: int) -> pd.DataFrame:
    provincia = canonical_provincia(provincia)
    df_hist = pd.read_sql(text(f"""
        SELECT anio, mes, SUM(total_homicidios) AS total_homicidios
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE provincia = :prov AND (anio < :anio OR (anio = :anio AND mes < :mes))
        GROUP BY anio, mes
        ORDER BY anio, mes
    """), engine, params={"prov": provincia, "anio": anio, "mes": mes})

    if len(df_hist) < 12:
        return None

    serie = df_hist["total_homicidios"].values.astype(float)

    lag_1  = serie[-1]  if len(serie) >= 1  else 0
    lag_3  = np.mean(serie[-3:])  if len(serie) >= 3  else np.mean(serie)
    lag_6  = np.mean(serie[-6:])  if len(serie) >= 6  else np.mean(serie)
    lag_12 = serie[-12] if len(serie) >= 12 else serie[0]

    media_movil_3 = np.mean(serie[-3:])
    media_movil_6 = np.mean(serie[-6:])

    serie_anio = df_hist[df_hist["anio"] == anio]["total_homicidios"].values
    acumulado = float(serie_anio.sum()) if len(serie_anio) > 0 else 0.0

    mismos_meses = df_hist[df_hist["mes"] == mes]["total_homicidios"].values
    mediana_hist = float(np.median(mismos_meses)) if len(mismos_meses) > 0 else float(np.mean(serie))

    provincia_cod = hom_prov_inv.get(provincia)
    if provincia_cod is None:
        return None

    row = {
        "anio": int(anio), "mes": int(mes), "provincia_cod": int(provincia_cod),
        "lag_1": float(lag_1), "lag_3": float(lag_3), "lag_6": float(lag_6), "lag_12": float(lag_12),
        "media_movil_3": float(media_movil_3), "media_movil_6": float(media_movil_6),
        "acumulado_anio": float(acumulado), "mediana_historica": float(mediana_hist),
    }
    return pd.DataFrame([row])[feature_cols]


# =========================================================
# ENDPOINTS DE DATOS
# =========================================================

@app.get("/homicidios/anual")
def homicidios_anual():
    df = pd.read_sql(f"""
        SELECT anio, SUM(total_homicidios) AS total
        FROM {DWH_SCHEMA}.cubo_homicidio
        GROUP BY anio ORDER BY anio
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/homicidios/provincia")
def homicidios_provincia():
    df = pd.read_sql(f"""
        SELECT provincia, SUM(total_homicidios) AS total
        FROM {DWH_SCHEMA}.cubo_homicidio
        GROUP BY provincia ORDER BY total DESC
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/homicidios/canton")
def homicidios_canton(provincia: str = None):
    if provincia:
        provincia = canonical_provincia(provincia)
        query = text("""
            SELECT canton, provincia, SUM(total_homicidios) AS total
            FROM dwh.cubo_homicidio
            WHERE provincia = :provincia
            GROUP BY canton, provincia ORDER BY total DESC LIMIT 20
        """)
        df = pd.read_sql(query, engine, params={"provincia": provincia})
    else:
        df = pd.read_sql("""
            SELECT canton, provincia, SUM(total_homicidios) AS total
            FROM dwh.cubo_homicidio
            GROUP BY canton, provincia ORDER BY total DESC LIMIT 20
        """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/homicidios/mensual")
def homicidios_mensual(provincia: str):
    provincia = canonical_provincia(provincia)
    query = text("""
        SELECT anio, mes, SUM(total_homicidios) AS total
        FROM dwh.cubo_homicidio
        WHERE provincia = :provincia
        GROUP BY anio, mes ORDER BY anio, mes
    """)
    df = pd.read_sql(query, engine, params={"provincia": provincia})
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/desapariciones/anual")
def desapariciones_anual():
    df = pd.read_sql(f"""
        SELECT anio_desaparicion AS anio,
               SUM(total_desapariciones) AS total_desapariciones,
               SUM(total_localizados) AS total_localizados
        FROM {DWH_SCHEMA}.cubo_desaparicion
        GROUP BY anio_desaparicion ORDER BY anio_desaparicion
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/armas/anual")
def armas_anual():
    df = pd.read_sql(f"""
        SELECT anio, SUM(total_armas) AS total_armas, SUM(total_eventos) AS total_eventos
        FROM {DWH_SCHEMA}.cubo_arma
        GROUP BY anio ORDER BY anio
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


@app.get("/defunciones/anual")
def defunciones_anual():
    df = pd.read_sql(f"""
        SELECT anio_fallecimiento AS anio,
               SUM(total_defunciones) AS total_defunciones,
               SUM(muertes_violentas) AS muertes_violentas
        FROM {DWH_SCHEMA}.cubo_defuncion
        GROUP BY anio_fallecimiento ORDER BY anio_fallecimiento
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


# =========================================================
# ENDPOINTS DE PREDICCION ML
# =========================================================

@app.get("/prediccion/homicidios")
def predecir_homicidios(
    provincia: str,
    anio: int,
    mes: int,
):
    provincia = canonical_provincia(provincia)
    X = calcular_features_provincia(provincia, anio, mes)
    if X is None:
        return {"error": "No hay suficiente historial para esta provincia. Se requiere al menos 12 meses de datos."}

    pred_rf  = max(0.0, float(rf_homicidios.predict(X)[0]))
    pred_xgb = max(0.0, float(xgb_homicidios.predict(X)[0]))
    return {
        "provincia": provincia,
        "anio": anio,
        "mes": mes,
        "prediccion_rf":  round(pred_rf, 1),
        "prediccion_xgb": round(pred_xgb, 1),
        "promedio":       round((pred_rf + pred_xgb) / 2, 1),
    }


@app.get("/prediccion/riesgo")
def predecir_riesgo(anio: int, provincia_cod: int, canton_cod: int, mes: int = 0):
    X = pd.DataFrame([[anio, provincia_cod, canton_cod]],
                      columns=['anio', 'provincia_cod', 'canton_cod'])
    riesgo = rf_riesgo.predict(X)[0]
    niveles = {0: 'BAJO', 1: 'MEDIO', 2: 'ALTO'}
    return {"nivel_riesgo": niveles.get(int(riesgo), 'DESCONOCIDO')}


# =========================================================
# PROVINCIAS
# =========================================================

@app.get("/provincias")
def get_provincias():
    return [
        {"provincia_cod": code, "provincia": name}
        for name, code in sorted(hom_prov_inv.items(), key=lambda x: x[0])
    ]


@app.get("/cantones")
def get_cantones(provincia: str = None):
    if provincia:
        provincia = canonical_provincia(provincia)
        query = text(f"""
            SELECT DISTINCT canton, provincia
            FROM {DWH_SCHEMA}.cubo_homicidio
            WHERE anio BETWEEN 2017 AND 2024 AND provincia = :provincia
            ORDER BY canton
        """)
        df = pd.read_sql(query, engine, params={"provincia": provincia})
    else:
        df = pd.read_sql(f"""
            SELECT DISTINCT canton, provincia
            FROM {DWH_SCHEMA}.cubo_homicidio
            WHERE anio BETWEEN 2017 AND 2024
            ORDER BY canton
        """, engine)

    return [{"canton": row["canton"], "provincia": row["provincia"]} for _, row in df.iterrows()]
