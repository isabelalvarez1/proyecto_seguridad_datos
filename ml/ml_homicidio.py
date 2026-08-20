import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb
import joblib
from utils.config import engine, DWH_SCHEMA

# ── 1. Cargar datos ───────────────────────────────────────
def cargar_datos():
    print("📦 Cargando datos del DW...")
    df = pd.read_sql(f"""
        SELECT 
            anio,
            mes,
            provincia,
            canton,
            sexo,
            rango_edad,
            tipo_arma,
            motivacion,
            SUM(total_homicidios) AS total_homicidios
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE anio BETWEEN 2017 AND 2024
        GROUP BY anio, mes, provincia, canton,
                 sexo, rango_edad, tipo_arma, motivacion
        ORDER BY anio, mes
    """, engine)
    print(f"✅ Datos cargados: {df.shape[0]} filas")
    return df

# ── 2. Preparar features ──────────────────────────────────
def preparar_features(df):
    print("🔧 Preparando features...")

    # Encoding de variables categóricas
    categorical_cols = {
        'provincia': 'provincia_cod',
        'canton': 'canton_cod',
        'sexo': 'sexo_cod',
        'rango_edad': 'rango_edad_cod',
        'tipo_arma': 'tipo_arma_cod',
        'motivacion': 'motivacion_cod',
    }

    mappings = {}
    for col, cod_col in categorical_cols.items():
        cat = df[col].astype('category')
        df[cod_col] = cat.cat.codes
        mappings[col] = dict(enumerate(cat.cat.categories))

    # Features y target
    X = df[['anio', 'mes', 'provincia_cod', 'canton_cod',
            'sexo_cod', 'rango_edad_cod', 'tipo_arma_cod', 'motivacion_cod']]
    y = df['total_homicidios']

    print(f"✅ Features: {X.shape[1]} variables")
    return X, y, df, mappings

# ── 3. Entrenar modelos ───────────────────────────────────
def entrenar_modelos(X, y, mappings):
    print("\n🤖 Entrenando modelos...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Random Forest
    print("   ⏳ Entrenando Random Forest...")
    rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    y_pred_rf = rf.predict(X_test)

    # XGBoost
    print("   ⏳ Entrenando XGBoost...")
    xgb_model = xgb.XGBRegressor(n_estimators=100, random_state=42)
    xgb_model.fit(X_train, y_train)
    y_pred_xgb = xgb_model.predict(X_test)

    # ── Métricas ──────────────────────────────────────────
    print("\n📊 MÉTRICAS RANDOM FOREST:")
    print(f"   MAE:  {mean_absolute_error(y_test, y_pred_rf):.2f}")
    print(f"   RMSE: {np.sqrt(mean_squared_error(y_test, y_pred_rf)):.2f}")
    print(f"   R²:   {r2_score(y_test, y_pred_rf):.4f}")

    print("\n📊 MÉTRICAS XGBOOST:")
    print(f"   MAE:  {mean_absolute_error(y_test, y_pred_xgb):.2f}")
    print(f"   RMSE: {np.sqrt(mean_squared_error(y_test, y_pred_xgb)):.2f}")
    print(f"   R²:   {r2_score(y_test, y_pred_xgb):.4f}")

    # ── Guardar modelos + mappings ────────────────────────
    os.makedirs('ml/modelos', exist_ok=True)
    joblib.dump(rf,        'ml/modelos/rf_homicidios.pkl')
    joblib.dump(xgb_model, 'ml/modelos/xgb_homicidios.pkl')
    joblib.dump(mappings,  'ml/modelos/mappings_homicidios.pkl')
    print("\n✅ Modelos y mappings guardados en ml/modelos/")

    return rf, xgb_model, X_test, y_test, y_pred_rf, y_pred_xgb

# ── 4. Graficar resultados ────────────────────────────────
def graficar_resultados(y_test, y_pred_rf, y_pred_xgb):
    print("\n📈 Generando gráficos...")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Random Forest
    axes[0].scatter(y_test, y_pred_rf, alpha=0.5, color='blue', s=10)
    axes[0].plot([y_test.min(), y_test.max()],
                 [y_test.min(), y_test.max()], 'r--', linewidth=2)
    axes[0].set_title(f'Random Forest\nR²={r2_score(y_test, y_pred_rf):.4f}')
    axes[0].set_xlabel('Real')
    axes[0].set_ylabel('Predicho')
    axes[0].grid(True, alpha=0.3)

    # XGBoost
    axes[1].scatter(y_test, y_pred_xgb, alpha=0.5, color='green', s=10)
    axes[1].plot([y_test.min(), y_test.max()],
                 [y_test.min(), y_test.max()], 'r--', linewidth=2)
    axes[1].set_title(f'XGBoost\nR²={r2_score(y_test, y_pred_xgb):.4f}')
    axes[1].set_xlabel('Real')
    axes[1].set_ylabel('Predicho')
    axes[1].grid(True, alpha=0.3)

    plt.suptitle('Comparación de Modelos: Real vs Predicho', fontsize=14)
    plt.tight_layout()
    plt.savefig('ml/modelos/comparacion_modelos.png', dpi=150)
    plt.show()
    print("✅ Gráfico guardado!")

# ── 5. Función principal ──────────────────────────────────
def modelo_homicidios():
    print("\n========================================")
    print("🤖 MODELO PREDICTIVO DE HOMICIDIOS")
    print("========================================")
    df                                                        = cargar_datos()
    X, y, df, mappings                                        = preparar_features(df)
    rf, xgb_m, X_test, y_test, y_pred_rf, y_pred_xgb         = entrenar_modelos(X, y, mappings)
    graficar_resultados(y_test, y_pred_rf, y_pred_xgb)
    print("\n✅ MODELO HOMICIDIOS COMPLETADO!")


    