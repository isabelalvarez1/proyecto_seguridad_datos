import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib

from utils.config import engine, DWH_SCHEMA

# ── 1. Cargar datos ───────────────────────────────────────
def cargar_datos():
    print("📦 Cargando datos para el Modelo de Riesgo...")
    # Extraemos un resumen por cantón y año
    # Usaremos el cubo_homicidio que ya tienes, agrupando por cantón
    df = pd.read_sql(f"""
        SELECT 
            anio,
            provincia,
            canton,
            SUM(total_homicidios) AS total_homicidios,
            -- Contamos cuántos homicidios usaron arma de fuego (ejemplo de feature)
            SUM(CASE WHEN tipo_arma ILIKE '%%fuego%%' THEN total_homicidios ELSE 0 END) as homicidios_arma_fuego
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE anio BETWEEN 2017 AND 2024
        GROUP BY anio, provincia, canton
    """, engine)
    print(f"✅ Datos cargados: {df.shape[0]} filas (cantones por año)")
    return df

# ── 2. Definir Nivel de Riesgo (Percentiles) ──────────────
def definir_nivel_riesgo(df):
    print("🔍 Definiendo niveles de riesgo usando Percentiles...")
    
    # Rellenar posibles nulos
    df = df.fillna(0)
    
    # Para balancear las clases, asignamos cada cantón a una de 3 categorías (Bajo, Medio, Alto)
    # según el volumen de homicidios que presenta en comparación al resto, usando percentiles.
    # Usamos rank(method='first') para desempatar los cantones que tienen el mismo número de homicidios.
    df['riesgo_target'] = pd.qcut(df['total_homicidios'].rank(method='first'), q=3, labels=[0, 1, 2])
    
    # Convertimos la variable categórica a número entero
    df['riesgo_target'] = df['riesgo_target'].astype(int)
    
    # Etiqueta en texto para gráficas
    etiquetas = {0: 'Bajo Riesgo', 1: 'Riesgo Medio', 2: 'Alto Riesgo'}
    df['riesgo_label'] = df['riesgo_target'].map(etiquetas)
    
    print("📊 Distribución balanceada de Niveles de Riesgo:")
    print(df['riesgo_label'].value_counts())
    
    # Ya no necesitamos retornar el modelo kmeans
    return df, None

# ── 3. Preparar features para clasificación ────────────────
def preparar_features(df):
    print("🔧 Preparando features para el modelo de clasificación...")

    # Encoding de variables categóricas
    df['provincia_cod'] = df['provincia'].astype('category').cat.codes
    df['canton_cod']    = df['canton'].astype('category').cat.codes

    # Features: predecimos el riesgo basados en la ubicación y el año
    X = df[['anio', 'provincia_cod', 'canton_cod']]
    y = df['riesgo_target']

    print(f"✅ Features: {X.shape[1]} variables")
    return X, y, df

# ── 4. Entrenar modelo de Clasificación ────────────────────
def entrenar_modelo(X, y):
    print("\n🤖 Entrenando Clasificador Random Forest...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    rf_class = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    rf_class.fit(X_train, y_train)
    y_pred = rf_class.predict(X_test)

    # ── Métricas ──────────────────────────────────────────
    print("\n📊 MÉTRICAS DEL CLASIFICADOR DE RIESGO:")
    print(f"   Exactitud (Accuracy): {accuracy_score(y_test, y_pred):.4f}")
    print("\nReporte Detallado:")
    print(classification_report(y_test, y_pred, labels=[0, 1, 2], target_names=['Bajo', 'Medio', 'Alto'], zero_division=0))

    # ── Guardar modelos ───────────────────────────────────
    os.makedirs('ml/modelos', exist_ok=True)
    joblib.dump(rf_class, 'ml/modelos/rf_clasificador_riesgo.pkl')
    print("✅ Modelo guardado en ml/modelos/rf_clasificador_riesgo.pkl")

    return rf_class, X_test, y_test, y_pred

# ── 5. Graficar resultados ────────────────────────────────
def graficar_resultados(df, y_test, y_pred):
    print("\n📈 Generando gráficos de Riesgo...")

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # 1. Gráfico de Clusters Originales (Distribución)
    sns.scatterplot(
        data=df, x='total_homicidios', y='homicidios_arma_fuego', 
        hue='riesgo_label', palette=['green', 'orange', 'red'], 
        alpha=0.7, ax=axes[0]
    )
    axes[0].set_title('Percentiles: Distribución del Riesgo')
    axes[0].set_xlabel('Total de Homicidios')
    axes[0].set_ylabel('Homicidios con Arma de Fuego')

    # 2. Matriz de Confusión del Clasificador
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=['Bajo', 'Medio', 'Alto'], 
                yticklabels=['Bajo', 'Medio', 'Alto'], ax=axes[1])
    axes[1].set_title('Matriz de Confusión: Predicción del Nivel')
    axes[1].set_xlabel('Predicción')
    axes[1].set_ylabel('Realidad')

    plt.tight_layout()
    plt.savefig('ml/modelos/analisis_riesgo.png', dpi=150)
    plt.show()
    print("✅ Gráfico guardado en ml/modelos/analisis_riesgo.png")

# ── 6. Función principal ──────────────────────────────────
def modelo_riesgo():
    print("\n========================================")
    print("🚨 MODELO DE PREDICCIÓN DE RIESGO CANTÓNAL")
    print("========================================")
    
    df = cargar_datos()
    df, modelo_kmeans = definir_nivel_riesgo(df)
    
    X, y, df = preparar_features(df)
    rf_model, X_test, y_test, y_pred = entrenar_modelo(X, y)
    
    graficar_resultados(df, y_test, y_pred)
    print("\n✅ MODELO DE RIESGO COMPLETADO!")


