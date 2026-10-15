import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

connection_url = URL.create(
    "postgresql+psycopg2",
    username=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", ""),
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    database=os.environ.get("DB_NAME", "staging"),
)

DWH_SCHEMA = "dwh"

engine = create_engine(connection_url)

# ── Tablas clean (origen para dimensiones/hechos) ──────────
CLEAN_TABLES = {
    "homicidio":     "clean.homicidio_limpia",
    "arma":          "clean.mdi_arma_limpia",
    "desaparicion":  "clean.mdi_desaparecido_limpia",
    "defuncion":     "clean.edg_limpia",
    "enemdu":        "clean.enemdu_limpia",
}
