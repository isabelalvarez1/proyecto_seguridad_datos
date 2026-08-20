import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import pandas as pd
import joblib
from utils.config import engine, DWH_SCHEMA

app = FastAPI(
    title="API Seguridad Pública Ecuador",
    description="API para consultar datos y predicciones de seguridad pública",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Cargar modelos + mappings ─────────────────────────────
rf_homicidios  = joblib.load('ml/modelos/rf_homicidios.pkl')
xgb_homicidios = joblib.load('ml/modelos/xgb_homicidios.pkl')
rf_riesgo      = joblib.load('ml/modelos/rf_clasificador_riesgo.pkl')
mappings_hom   = joblib.load('ml/modelos/mappings_homicidios.pkl')
mappings_riesgo = joblib.load('ml/modelos/mappings_riesgo.pkl')

# Invertir mappings: {code: name} → {name: code}
hom_prov_inv = {v: k for k, v in mappings_hom['provincia'].items()}
hom_canton_inv = {v: k for k, v in mappings_hom['canton'].items()}
riesgo_prov_inv = {v: k for k, v in mappings_riesgo['provincia'].items()}
riesgo_canton_inv = {v: k for k, v in mappings_riesgo['canton'].items()}

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
               SUM(total_muertes_violentas) AS muertes_violentas
        FROM {DWH_SCHEMA}.cubo_defuncion
        GROUP BY anio_fallecimiento ORDER BY anio_fallecimiento
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')


# =========================================================
# ENDPOINTS DE PREDICCIÓN ML
# =========================================================

@app.get("/prediccion/homicidios")
def predecir_homicidios(
    anio: int, mes: int, provincia_cod: int, canton_cod: int,
    sexo_cod: int = 0, rango_edad_cod: int = 0,
    tipo_arma_cod: int = 0, motivacion_cod: int = 0
):
    X = pd.DataFrame([[anio, mes, provincia_cod, canton_cod,
                        sexo_cod, rango_edad_cod, tipo_arma_cod, motivacion_cod]],
                      columns=['anio', 'mes', 'provincia_cod', 'canton_cod',
                               'sexo_cod', 'rango_edad_cod', 'tipo_arma_cod', 'motivacion_cod'])
    pred_rf  = max(0.0, float(rf_homicidios.predict(X)[0]))
    pred_xgb = max(0.0, float(xgb_homicidios.predict(X)[0]))
    return {
        "prediccion_rf":  round(pred_rf, 2),
        "prediccion_xgb": round(pred_xgb, 2),
        "promedio":       round((pred_rf + pred_xgb) / 2, 2)
    }


@app.get("/prediccion/riesgo")
def predecir_riesgo(anio: int, provincia_cod: int, canton_cod: int, mes: int = 0):
    X = pd.DataFrame([[anio, provincia_cod, canton_cod]],
                      columns=['anio', 'provincia_cod', 'canton_cod'])
    riesgo = rf_riesgo.predict(X)[0]
    niveles = {0: 'BAJO', 1: 'MEDIO', 2: 'ALTO'}
    return {"nivel_riesgo": niveles.get(int(riesgo), 'DESCONOCIDO')}


# =========================================================
# PROVINCIAS / CANTONES (usando mappings del entrenamiento)
# =========================================================

@app.get("/provincias")
def get_provincias():
    return [
        {"provincia_cod": code, "provincia": name}
        for name, code in sorted(hom_prov_inv.items())
    ]


@app.get("/cantones")
def get_cantones(provincia: str = None):
    df = pd.read_sql(f"""
        SELECT DISTINCT canton, provincia
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE anio BETWEEN 2017 AND 2024
        {"AND provincia = :provincia" if provincia else ""}
        ORDER BY canton
    """, engine, params={"provincia": provincia} if provincia else {})

    results = []
    for _, row in df.iterrows():
        canton_name = row['canton']
        prov_name = row['provincia']
        canton_code = hom_canton_inv.get(canton_name)
        if canton_code is not None:
            results.append({
                "canton_cod": canton_code,
                "canton": canton_name,
                "provincia": prov_name
            })

    return results
