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

# ── CORS (permite conexión desde la página web) ───────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Cargar modelos ML ─────────────────────────────────────
rf_homicidios  = joblib.load('ml/modelos/rf_homicidios.pkl')
xgb_homicidios = joblib.load('ml/modelos/xgb_homicidios.pkl')
rf_riesgo      = joblib.load('ml/modelos/rf_clasificador_riesgo.pkl')

# =========================================================
# ENDPOINTS DE DATOS
# =========================================================

# ── 1. Homicidios por año ─────────────────────────────────
@app.get("/homicidios/anual")
def homicidios_anual():
    df = pd.read_sql(f"""
        SELECT 
            anio,
            SUM(total_homicidios) AS total
        FROM {DWH_SCHEMA}.cubo_homicidio
        GROUP BY anio
        ORDER BY anio
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# ── 2. Homicidios por provincia ───────────────────────────
@app.get("/homicidios/provincia")
def homicidios_provincia():
    df = pd.read_sql(f"""
        SELECT 
            provincia,
            SUM(total_homicidios) AS total
        FROM {DWH_SCHEMA}.cubo_homicidio
        GROUP BY provincia
        ORDER BY total DESC
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# ── 3. Homicidios por canton ──────────────────────────────
@app.get("/homicidios/canton")
def homicidios_canton(provincia: str = None):
    if provincia:
        query = text(f"""
            SELECT canton, provincia, SUM(total_homicidios) AS total
            FROM {DWH_SCHEMA}.cubo_homicidio
            WHERE provincia = :provincia
            GROUP BY canton, provincia
            ORDER BY total DESC
            LIMIT 20
        """)
        df = pd.read_sql(query, engine, params={"provincia": provincia})
    else:
        df = pd.read_sql(f"""
            SELECT canton, provincia, SUM(total_homicidios) AS total
            FROM {DWH_SCHEMA}.cubo_homicidio
            GROUP BY canton, provincia
            ORDER BY total DESC
            LIMIT 20
        """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# ── 4. Desapariciones por año ─────────────────────────────
@app.get("/desapariciones/anual")
def desapariciones_anual():
    df = pd.read_sql(f"""
        SELECT 
            anio_desaparicion       AS anio,
            SUM(total_desapariciones) AS total_desapariciones,
            SUM(total_localizados)    AS total_localizados
        FROM {DWH_SCHEMA}.cubo_desaparicion
        GROUP BY anio_desaparicion
        ORDER BY anio_desaparicion
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# ── 5. Armas por año ──────────────────────────────────────
@app.get("/armas/anual")
def armas_anual():
    df = pd.read_sql(f"""
        SELECT 
            anio,
            SUM(total_armas)   AS total_armas,
            SUM(total_eventos) AS total_eventos
        FROM {DWH_SCHEMA}.cubo_arma
        GROUP BY anio
        ORDER BY anio
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# ── 6. Defunciones por año ────────────────────────────────
@app.get("/defunciones/anual")
def defunciones_anual():
    df = pd.read_sql(f"""
        SELECT 
            anio_fallecimiento          AS anio,
            SUM(total_defunciones)      AS total_defunciones,
            SUM(total_muertes_violentas) AS muertes_violentas
        FROM {DWH_SCHEMA}.cubo_defuncion
        GROUP BY anio_fallecimiento
        ORDER BY anio_fallecimiento
    """, engine)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient='records')

# =========================================================
# ENDPOINTS DE PREDICCIÓN ML
# =========================================================

# ── 7. Predicción de homicidios ───────────────────────────
@app.get("/prediccion/homicidios")
def predecir_homicidios(
    anio: int,
    mes: int,
    provincia_cod: int,
    canton_cod: int,
    sexo_cod: int = 0,
    rango_edad_cod: int = 0,
    tipo_arma_cod: int = 0,
    motivacion_cod: int = 0
):
    X = pd.DataFrame([[anio, mes, provincia_cod, canton_cod,
                       sexo_cod, rango_edad_cod, tipo_arma_cod, motivacion_cod]],
                     columns=['anio', 'mes', 'provincia_cod', 'canton_cod',
                              'sexo_cod', 'rango_edad_cod', 'tipo_arma_cod', 'motivacion_cod'])
    # Asegurar que las predicciones no sean negativas
    pred_rf  = max(0.0, float(rf_homicidios.predict(X)[0]))
    pred_xgb = max(0.0, float(xgb_homicidios.predict(X)[0]))
    return {
        "prediccion_rf":  round(pred_rf, 2),
        "prediccion_xgb": round(pred_xgb, 2),
        "promedio":       round((pred_rf + pred_xgb) / 2, 2)
    }

# ── 8. Clasificación de riesgo ────────────────────────────
@app.get("/prediccion/riesgo")
def predecir_riesgo(
    anio: int,
    provincia_cod: int,
    canton_cod: int,
    mes: int = 0  # Param for backwards compatibility, ignored in model
):
    X = pd.DataFrame([[anio, provincia_cod, canton_cod]],
                     columns=['anio', 'provincia_cod', 'canton_cod'])
    riesgo = rf_riesgo.predict(X)[0]
    niveles = {0: 'BAJO', 1: 'MEDIO', 2: 'ALTO'}
    return {
        "nivel_riesgo": niveles.get(int(riesgo), 'DESCONOCIDO')
    }
# ── Provincias disponibles ────────────────────────────────
@app.get("/provincias")
def get_provincias():
    df = pd.read_sql(f"""
        SELECT provincia_cod, provincia
        FROM (
            SELECT provincia,
                   DENSE_RANK() OVER (ORDER BY provincia) - 1 AS provincia_cod
            FROM {DWH_SCHEMA}.cubo_homicidio
            WHERE anio BETWEEN 2017 AND 2024
        ) t
        GROUP BY provincia_cod, provincia
        ORDER BY provincia
    """, engine)
    df = df.fillna(0)
    return df.to_dict(orient='records')

# ── Cantones por provincia ────────────────────────────────
@app.get("/cantones")
def get_cantones(provincia: str = None):
    if provincia:
        query = text(f"""
            SELECT canton_cod, canton, provincia
            FROM (
                SELECT canton, provincia,
                       DENSE_RANK() OVER (ORDER BY canton) - 1 AS canton_cod
                FROM {DWH_SCHEMA}.cubo_homicidio
                WHERE anio BETWEEN 2017 AND 2024
            ) t
            WHERE provincia = :provincia
            GROUP BY canton_cod, canton, provincia
            ORDER BY canton
        """)
        df = pd.read_sql(query, engine, params={"provincia": provincia})
    else:
        df = pd.read_sql(f"""
            SELECT canton_cod, canton, provincia
            FROM (
                SELECT canton, provincia,
                       DENSE_RANK() OVER (ORDER BY canton) - 1 AS canton_cod
                FROM {DWH_SCHEMA}.cubo_homicidio
                WHERE anio BETWEEN 2017 AND 2024
            ) t
            GROUP BY canton_cod, canton, provincia
            ORDER BY canton
        """, engine)
    df = df.fillna(0)
    return df.to_dict(orient='records')
