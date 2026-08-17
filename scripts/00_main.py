# =========================================================
# MAIN PIPELINE RUNNER
# Punto de entrada principal del sistema
# =========================================================
import sys
from pathlib import Path
import uvicorn

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api.api_seguridad import app
from ml.modelo_riesgo import modelo_riesgo
from ml.ml_desapariciones import modelo_desapariciones
from ml.ml_homicidio import modelo_homicidios
from scripts.create_dwh import create_dwh
from scripts.load_hechos import load_all_facts


def main():
    print("\n========================================")
    print("INICIANDO SISTEMA DE SEGURIDAD")
    print("========================================")

    # create_dwh()
    # load_all_facts()
    # modelo_homicidios()
    # modelo_riesgo()
    # modelo_desapariciones()

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()