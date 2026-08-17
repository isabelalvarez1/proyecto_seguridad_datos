from utils.config import engine, DWH_SCHEMA
import pandas as pd

df = pd.read_sql(f"""
    SELECT provincia, canton
    FROM {DWH_SCHEMA}.cubo_homicidio
    WHERE anio BETWEEN 2017 AND 2024
""", engine)

df['provincia_cod'] = df['provincia'].astype('category').cat.codes
df['canton_cod']    = df['canton'].astype('category').cat.codes

cats_py = df[['canton', 'canton_cod', 'provincia']].drop_duplicates().sort_values('canton').reset_index(drop=True)

df_sql = pd.read_sql(f"""
    SELECT canton_cod, canton, provincia
    FROM (
        SELECT canton, provincia,
               DENSE_RANK() OVER (ORDER BY canton) - 1 AS canton_cod
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE anio BETWEEN 2017 AND 2024
    ) t
    GROUP BY canton_cod, canton, provincia
    ORDER BY canton_cod
""", engine)

print("PYTHON CODES:")
print(cats_py.head())

print("\nSQL CODES:")
print(df_sql.head())

# Also let's check what the user's current code does
df_user = pd.read_sql(f"""
    SELECT DISTINCT canton_cod, canton, provincia
    FROM (
        SELECT ROW_NUMBER() OVER (PARTITION BY canton 
               ORDER BY canton) - 1 AS canton_cod,
               canton, provincia
        FROM {DWH_SCHEMA}.cubo_homicidio
        WHERE provincia = 'AZUAY'
    ) t
    ORDER BY canton
    LIMIT 5
""", engine)
print("\nUSER SQL CODES (AZUAY):")
print(df_user)
