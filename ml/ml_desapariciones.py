import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, mean_absolute_error, r2_score
import joblib

from utils.config import engine, DWH_SCHEMA
from sqlalchemy import text

# =====================================================================
# MODELO 1: CLASIFICACIÓN (PROBABILIDAD DE SER LOCALIZADO)
# =====================================================================
def modelo_clasificacion_localizacion():
    print("\n" + "="*50)
    print("🕵️ MODELO 1: PROBABILIDAD DE LOCALIZACIÓN")
    print("="*50)
    
    # 1. Cargar Datos
    print("📦 Cargando datos del cubo_desaparicion...")
    query = text(f"""
        SELECT 
            provincia, canton, sexo, rango_edad, etnia,
            situacion_actual,
            SUM(total_desapariciones) as total
        FROM {DWH_SCHEMA}.cubo_desaparicion
        WHERE anio_desaparicion BETWEEN 2017 AND 2024
        GROUP BY provincia, canton, sexo, rango_edad, etnia, situacion_actual
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    # 2. Preparar Target
    # Asumimos que "LOCALIZADO" es el éxito (1), cualquier otra cosa es (0)
    df['is_localizado'] = np.where(df['situacion_actual'].str.upper() == 'LOCALIZADO', 1, 0)
    
    # 3. Preparar Features (Codificación Categórica)
    features = ['provincia', 'canton', 'sexo', 'rango_edad', 'etnia']
    df_encoded = df.copy()
    
    # Convertir a variables numéricas y guardar mappings
    mappings_clf = {}
    for col in features:
        cat = df_encoded[col].astype('category')
        df_encoded[col] = cat.cat.codes
        mappings_clf[col] = dict(enumerate(cat.cat.categories))
        
    X = df_encoded[features]
    y = df_encoded['is_localizado']
    weights = df_encoded['total'] # Usamos el conteo como peso para que las filas con muchos casos pesen más
    
    # 4. Entrenar
    print("🤖 Entrenando Random Forest Classifier...")
    X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
        X, y, weights, test_size=0.2, random_state=42
    )
    
    rf_clf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    rf_clf.fit(X_train, y_train, sample_weight=w_train)
    
    y_pred = rf_clf.predict(X_test)
    
    # 5. Métricas
    print("\n📊 MÉTRICAS DEL CLASIFICADOR:")
    print(classification_report(y_test, y_pred, labels=[0, 1], sample_weight=w_test, target_names=['No Localizado', 'Localizado'], zero_division=0))
    
    # Matriz de confusión
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1], sample_weight=w_test)
    
    # 6. Importancia de Variables
    importances = rf_clf.feature_importances_
    
    # Guardar modelo + mappings
    os.makedirs('ml/modelos', exist_ok=True)
    joblib.dump(rf_clf, 'ml/modelos/rf_desapariciones_clasificador.pkl')
    joblib.dump(mappings_clf, 'ml/modelos/mappings_desapariciones_clf.pkl')
    print("✅ Modelo Clasificador guardado en ml/modelos/")
    
    return features, importances, cm, mappings_clf

# =====================================================================
# MODELO 2: REGRESIÓN (PRONÓSTICO DE VOLUMEN)
# =====================================================================
def modelo_regresion_volumen():
    print("\n" + "="*50)
    print("📈 MODELO 2: PRONÓSTICO DE VOLUMEN DE DESAPARECIDOS")
    print("="*50)
    
    # 1. Cargar Datos
    print("📦 Cargando datos agregados por cantón y año...")
    query = text(f"""
        SELECT 
            anio_desaparicion as anio,
            provincia,
            canton,
            SUM(total_desapariciones) as total_desapariciones
        FROM {DWH_SCHEMA}.cubo_desaparicion
        WHERE anio_desaparicion BETWEEN 2017 AND 2024
        GROUP BY anio_desaparicion, provincia, canton
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
        
    df = df.fillna(0)
    
    # 2. Preparar Features
    mappings_reg = {}
    for col in ['provincia', 'canton']:
        cat = df[col].astype('category')
        df[f'{col}_cod'] = cat.cat.codes
        mappings_reg[col] = dict(enumerate(cat.cat.categories))
    
    X = df[['anio', 'provincia_cod', 'canton_cod']]
    y = df['total_desapariciones']
    
    # 3. Entrenar
    print("🤖 Entrenando Random Forest Regressor...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    rf_reg = RandomForestRegressor(n_estimators=100, random_state=42)
    rf_reg.fit(X_train, y_train)
    
    y_pred = rf_reg.predict(X_test)
    
    # 4. Métricas
    print("\n📊 MÉTRICAS DEL REGRESOR:")
    print(f"   MAE (Error Absoluto Medio): {mean_absolute_error(y_test, y_pred):.2f} casos")
    print(f"   R² (Precisión de tendencia):  {r2_score(y_test, y_pred):.4f}")
    
    # Guardar
    joblib.dump(rf_reg, 'ml/modelos/rf_desapariciones_regresor.pkl')
    joblib.dump(mappings_reg, 'ml/modelos/mappings_desapariciones_reg.pkl')
    print("✅ Modelo Regresor guardado en ml/modelos/")
    
    return y_test, y_pred, mappings_reg

# =====================================================================
# GRÁFICOS COMBINADOS
# =====================================================================
def graficar_resultados(features, importances, cm, y_test_reg, y_pred_reg):
    print("\n🎨 Generando gráficos analíticos...")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # 1. Importancia de Variables (Clasificador)
    # Seaborn barplot puede tener problemas si no pasamos el hue explícitamente en nuevas versiones, lo hacemos de forma estándar.
    sns.barplot(x=importances, y=features, ax=axes[0], hue=features, legend=False, palette='viridis')
    axes[0].set_title('¿Qué factor influye más en localizar\na alguien?')
    axes[0].set_xlabel('Nivel de Importancia')
    
    # 2. Matriz de Confusión (Clasificador)
    sns.heatmap(cm, annot=True, fmt='.0f', cmap='Blues',
                xticklabels=['No Localizado', 'Localizado'], 
                yticklabels=['No Localizado', 'Localizado'], ax=axes[1])
    axes[1].set_title('Efectividad del Modelo:\nPredicción vs Realidad')
    axes[1].set_ylabel('Realidad')
    axes[1].set_xlabel('Predicción')
    
    # 3. Dispersión Real vs Predicho (Regresor)
    axes[2].scatter(y_test_reg, y_pred_reg, alpha=0.5, color='orange')
    axes[2].plot([y_test_reg.min(), y_test_reg.max()], [y_test_reg.min(), y_test_reg.max()], 'r--', linewidth=2)
    axes[2].set_title('Pronóstico de Casos por Cantón')
    axes[2].set_xlabel('Casos Reales')
    axes[2].set_ylabel('Casos Predichos')
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('ml/modelos/analisis_desapariciones.png', dpi=150)
    plt.show()
    print("✅ Gráficos guardados en ml/modelos/analisis_desapariciones.png")

# =====================================================================
# FUNCIÓN PRINCIPAL
# =====================================================================
def modelo_desapariciones():
    print("\n" + "="*50)
    print("🌟 INICIANDO MODELOS DE DESAPARICIONES")
    print("="*50)
    
    # Ejecutar ambos modelos
    features, importances, cm, mappings_clf = modelo_clasificacion_localizacion()
    y_test_reg, y_pred_reg, mappings_reg = modelo_regresion_volumen()
    
    # Graficar resultados combinados
    graficar_resultados(features, importances, cm, y_test_reg, y_pred_reg)
    
    print("\n✅ TODOS LOS MODELOS DE DESAPARICIONES COMPLETADOS!")

