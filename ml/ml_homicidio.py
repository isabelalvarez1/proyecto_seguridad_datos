import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb
import joblib
from utils.config import engine, DWH_SCHEMA


# ── 1. Cargar datos agregados por provincia + mes ──────────
def cargar_datos():
    print("Cargando datos del cubo...")
    df = pd.read_sql(f"""
        SELECT
            anio,
            mes,
            provincia,
            SUM(total_homicidios) AS total_homicidios
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE anio BETWEEN 2017 AND 2024
        GROUP BY anio, mes, provincia
        ORDER BY provincia, anio, mes
    """, engine)
    print(f"Datos cargados: {df.shape[0]} filas ({df['provincia'].nunique()} provincias)")
    return df


# ── 2. Features de tendencia temporal (lags) ───────────────
def agregar_features_temporales(df):
    print("Agregando features de tendencia...")
    df = df.sort_values(["provincia", "anio", "mes"]).copy()

    # Lag de 1, 3, 6 y 12 meses por provincia
    for lag in [1, 3, 6, 12]:
        df[f"lag_{lag}"] = df.groupby("provincia")["total_homicidios"].shift(lag)

    # Media movil de 3 y 6 meses
    for w in [3, 6]:
        df[f"media_movil_{w}"] = (
            df.groupby("provincia")["total_homicidios"]
            .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
        )

    # Acumulado del año en curso
    df["anio_key"] = df["anio"]
    df["acumulado_anio"] = df.groupby(["provincia", "anio"])["total_homicidios"].cumsum()

    # Tasa de crecimiento interanual (mismo mes, año anterior)
    df["mismo_mes_anio_ant"] = df.groupby(["provincia", "mes"])["total_homicidios"].shift(1)
    df["tasa_crecimiento"] = (df["total_homicidios"] - df["mismo_mes_anio_ant"]) / df["mismo_mes_anio_ant"].replace(0, np.nan)

    # Mediana histórica de la provincia por mes
    df["mediana_historica"] = df.groupby(["provincia", "mes"])["total_homicidios"].transform(
        lambda x: x.expanding().median().shift(1)
    )

    return df


# ── 3. Preparar features ──────────────────────────────────
def preparar_features(df):
    print("Preparando features...")

    # Encoding de provincia
    cat_prov = df["provincia"].astype("category")
    df["provincia_cod"] = cat_prov.cat.codes
    mappings = {"provincia": dict(enumerate(cat_prov.cat.categories))}

    # Features
    feature_cols = [
        "anio", "mes", "provincia_cod",
        "lag_1", "lag_3", "lag_6", "lag_12",
        "media_movil_3", "media_movil_6",
        "acumulado_anio", "mediana_historica",
    ]

    X = df[feature_cols].copy()
    y = df["total_homicidios"].copy()

    # Eliminar filas con NaN en features (primeros meses sin lag)
    mask = X.notna().all(axis=1)
    X = X[mask]
    y = y[mask]
    df = df[mask]

    print(f"Features: {X.shape[1]} variables, {len(X)} registros de entrenamiento")
    return X, y, df, mappings, feature_cols


# ── 4. Entrenar modelos ───────────────────────────────────
def entrenar_modelos(X, y, mappings, feature_cols):
    print("\nEntrenando modelos...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Random Forest
    print("  Entrenando Random Forest...")
    rf = RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_leaf=5,
        random_state=42, n_jobs=-1
    )
    rf.fit(X_train, y_train)
    y_pred_rf = rf.predict(X_test)

    # XGBoost (objective reg:squarederror, con regularization para no predecir negativos)
    print("  Entrenando XGBoost...")
    xgb_model = xgb.XGBRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        objective="reg:squarederror",
        min_child_weight=10, subsample=0.8, colsample_bytree=0.8,
        gamma=1.0, reg_alpha=1.0, reg_lambda=1.0,
        random_state=42,
    )
    xgb_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    y_pred_xgb = xgb_model.predict(X_test)

    # Clip predicciones a minimo 0
    y_pred_rf = np.clip(y_pred_rf, 0, None)
    y_pred_xgb = np.clip(y_pred_xgb, 0, None)

    # Metricas
    print("\n--- RANDOM FOREST ---")
    print(f"  MAE:  {mean_absolute_error(y_test, y_pred_rf):.2f}")
    print(f"  RMSE: {np.sqrt(mean_squared_error(y_test, y_pred_rf)):.2f}")
    print(f"  R2:   {r2_score(y_test, y_pred_rf):.4f}")

    print("\n--- XGBOOST ---")
    print(f"  MAE:  {mean_absolute_error(y_test, y_pred_xgb):.2f}")
    print(f"  RMSE: {np.sqrt(mean_squared_error(y_test, y_pred_xgb)):.2f}")
    print(f"  R2:   {r2_score(y_test, y_pred_xgb):.4f}")

    # Feature importance
    print("\n--- IMPORTANCIA DE VARIABLES (RF) ---")
    imp = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    for feat, val in imp.items():
        print(f"  {feat:25s}: {val:.4f}")

    # Guardar
    os.makedirs("ml/modelos", exist_ok=True)
    joblib.dump(rf, "ml/modelos/rf_homicidios.pkl")
    joblib.dump(xgb_model, "ml/modelos/xgb_homicidios.pkl")
    joblib.dump(mappings, "ml/modelos/mappings_homicidios.pkl")
    joblib.dump(feature_cols, "ml/modelos/features_homicidios.pkl")
    print("\nModelos y mappings guardados.")

    return rf, xgb_model, X_test, y_test, y_pred_rf, y_pred_xgb


# ── 5. Graficar ───────────────────────────────────────────
def graficar_resultados(y_test, y_pred_rf, y_pred_xgb):
    print("\nGenerando graficos...")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].scatter(y_test, y_pred_rf, alpha=0.5, color="blue", s=10)
    axes[0].plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], "r--", lw=2)
    axes[0].set_title(f"Random Forest\nR2={r2_score(y_test, y_pred_rf):.4f}")
    axes[0].set_xlabel("Real")
    axes[0].set_ylabel("Predicho")
    axes[0].grid(True, alpha=0.3)

    axes[1].scatter(y_test, y_pred_xgb, alpha=0.5, color="green", s=10)
    axes[1].plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], "r--", lw=2)
    axes[1].set_title(f"XGBoost\nR2={r2_score(y_test, y_pred_xgb):.4f}")
    axes[1].set_xlabel("Real")
    axes[1].set_ylabel("Predicho")
    axes[1].grid(True, alpha=0.3)

    plt.suptitle("Comparacion de Modelos: Real vs Predicho (provincia+mes)", fontsize=14)
    plt.tight_layout()
    plt.savefig("ml/modelos/comparacion_modelos.png", dpi=150)
    plt.close()
    print("Grafico guardado!")


# ── 6. Principal ──────────────────────────────────────────
def modelo_homicidios():
    print("\n" + "=" * 50)
    print("  MODELO PREDICTIVO DE HOMICIDIOS")
    print("=" * 50)
    df = cargar_datos()
    df = agregar_features_temporales(df)
    X, y, df, mappings, feature_cols = preparar_features(df)
    rf, xgb_m, X_test, y_test, y_pred_rf, y_pred_xgb = entrenar_modelos(X, y, mappings, feature_cols)
    graficar_resultados(y_test, y_pred_rf, y_pred_xgb)
    print("\nMODELO COMPLETADO!")


if __name__ == "__main__":
    modelo_homicidios()
