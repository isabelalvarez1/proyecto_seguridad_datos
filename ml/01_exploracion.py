import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from utils.config import engine, DWH_SCHEMA

print("✅ Conexión lista!")

# ── 1. Cargar datos del cubo homicidios ──────────────────
df_homicidios = pd.read_sql(f"""
    SELECT 
        anio,
        provincia,
        canton,
        sexo,
        rango_edad,
        tipo_arma,
        motivacion,
        SUM(total_homicidios) AS total
    FROM {DWH_SCHEMA}.cubo_homicidio
    WHERE anio BETWEEN 2017 AND 2025
    GROUP BY anio, provincia, canton, 
             sexo, rango_edad, tipo_arma, motivacion
    ORDER BY anio, provincia
""", engine)

print(f"✅ Datos cargados: {df_homicidios.shape[0]} filas")
print(df_homicidios.head())

# ── 2. Resumen estadístico ────────────────────────────────
print("\n📊 Estadísticas básicas:")
print(df_homicidios.groupby('anio')['total'].sum())

# ── 3. Tendencia anual ────────────────────────────────────
tendencia = df_homicidios.groupby('anio')['total'].sum().reset_index()

plt.figure(figsize=(12, 5))
plt.plot(tendencia['anio'], tendencia['total'],
         marker='o', color='red', linewidth=2, markersize=8)
plt.fill_between(tendencia['anio'], tendencia['total'], alpha=0.2, color='red')
plt.title('Tendencia de Homicidios en Ecuador 2017-2025', fontsize=14)
plt.xlabel('Año')
plt.ylabel('Total Homicidios')
plt.grid(True, alpha=0.3)
plt.tight_layout()
os.makedirs('ml/modelos', exist_ok=True)
plt.savefig('ml/modelos/tendencia_homicidios.png', dpi=150)
plt.show()
print("✅ Gráfico guardado!")

# ── 4. Top 10 provincias ──────────────────────────────────
top_provincias = df_homicidios.groupby('provincia')['total'].sum()\
                                .sort_values(ascending=False)\
                                .head(10).reset_index()

plt.figure(figsize=(12, 6))
sns.barplot(data=top_provincias, x='total', y='provincia', palette='Reds_r')
plt.title('Top 10 Provincias con más Homicidios 2017-2025', fontsize=14)
plt.xlabel('Total Homicidios')
plt.ylabel('Provincia')
plt.tight_layout()
plt.savefig('ml/modelos/top_provincias.png', dpi=150)
plt.show()
print("✅ Gráfico Top Provincias guardado!")

# ── 5. Distribución por sexo ──────────────────────────────
por_sexo = df_homicidios.groupby('sexo')['total'].sum().reset_index()

plt.figure(figsize=(10, 8))
colores = ['#2196F3', '#F44336', '#9E9E9E', '#FF9800']

wedges, texts, autotexts = plt.pie(
    por_sexo['total'],
    labels=None,                    # quitamos labels del pie
    autopct='%1.1f%%',
    colors=colores,
    startangle=90,
    pctdistance=0.75,
    wedgeprops={'edgecolor': 'white', 'linewidth': 2}
)

# Leyenda separada para que no se encime
plt.legend(
    wedges,
    por_sexo['sexo'],
    title="Sexo",
    loc="center left",
    bbox_to_anchor=(1, 0, 0.5, 1),
    fontsize=12
)

plt.title('Homicidios por Sexo 2017-2025', fontsize=14, pad=20)
plt.tight_layout()
plt.savefig('ml/modelos/homicidios_sexo.png', dpi=150, bbox_inches='tight')
plt.show()
print("✅ Gráfico por Sexo guardado!")