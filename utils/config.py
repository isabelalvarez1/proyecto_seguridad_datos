import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

connection_url = URL.create(
    "postgresql+psycopg2",
    username=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "admin"),
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    database=os.environ.get("DB_NAME", "staging"),
)
# Esquemas
#RAW_SCHEMA = "raw"
#CLEAN_SCHEMA = "clean"
DWH_SCHEMA = "dwh"

engine = create_engine(connection_url)
    # -----------------------------------------------------
    # 🔫 ARMA
    # -----------------------------------------------------
TABLE = "raw.mdi_arma"
OUT_SCHEMA = "clean"
OUT_TABLE_ARMA = "mdi_arma_limpia"
    # -----------------------------------------------------
    # 🔫 DESAPARECIDO
    # -----------------------------------------------------
IN_TABLE_DESAPARECIDO = "raw.mdi_desaparecido"          # origen (cámbialo si está en otro esquema)
OUT_TABLE_DESAPARECIDO = "mdi_desaparecido_limpia"
    # -----------------------------------------------------
    # 🔫 EDG
    # -----------------------------------------------------
IN_TABLE_EDG = "raw.edg"          # origen (cámbialo si está en otro esquema)
OUT_TABLE_EDG = "edg_limpia"
    # -----------------------------------------------------
    # 🔫 ENEMDU
    # -----------------------------------------------------
IN_TABLE_ENEMDU = "raw.enemdu"          # origen (cámbialo si está en otro esquema)
OUT_TABLE_ENEMDU = "enemdu_limpia"
    # -----------------------------------------------------
    # 🔫 HOMICIDIO
    # -----------------------------------------------------
IN_TABLE_HOMICIDIO = "raw.mdi_homicidio"          # origen (cámbialo si está en otro esquema)
OUT_TABLE_HOMICIDIO = "homicidio_limpia"