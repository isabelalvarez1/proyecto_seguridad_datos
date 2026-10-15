# =========================================================
# Lanzador de API conservado por compatibilidad.
# Pipeline de datos: python -m scripts.run_pipeline
# =========================================================
import sys
from pathlib import Path
import uvicorn

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def main():
    print("\n========================================")
    print("INICIANDO SISTEMA DE SEGURIDAD")
    print("========================================")

    uvicorn.run("api.api_seguridad:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
