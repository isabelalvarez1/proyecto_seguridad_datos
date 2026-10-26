"""
Pipeline completo: Dimensiones → Hechos → Cubos OLAP
Uso:  python scripts/run_pipeline.py
"""
import sys, time
import argparse
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from scripts.load_dimensiones import (
    load_dim_tiempo,
    load_dim_ubicacion,
    load_dim_persona,
    load_dim_geo_punto,
    load_dim_arma,
    load_dim_delito,
    load_dim_motivacion,
    load_dim_estado_caso,
)
from scripts.load_hechos import (
    load_fact_homicidio,
    load_fact_arma,
    load_fact_desaparicion,
    load_fact_defuncion,
    load_fact_enemdu,
)
from scripts.create_cubes import refresh_all_cubes
from utils.dwh_helpers import truncate_dwh

DIMENSIONES = [
    ("dim_tiempo",       load_dim_tiempo),
    ("dim_ubicacion",    load_dim_ubicacion),
    ("dim_persona",      load_dim_persona),
    ("dim_geo_punto",    load_dim_geo_punto),
    ("dim_arma",         load_dim_arma),
    ("dim_delito",       load_dim_delito),
    ("dim_motivacion",   load_dim_motivacion),
    ("dim_estado_caso",  load_dim_estado_caso),
]

HECHOS = [
    ("fact_homicidio",     load_fact_homicidio),
    ("fact_arma",          load_fact_arma),
    ("fact_desaparicion",  load_fact_desaparicion),
    ("fact_defuncion",     load_fact_defuncion),
    ("fact_enemdu",        load_fact_enemdu),
]


def run(paso="todos", legacy=False):
    if paso not in ("todos", "dims", "facts", "cubos"):
        raise ValueError(f"Paso desconocido: {paso}")
    if not legacy:
        # El nuevo contrato clean conserva nulos/estados y requiere el mart web.
        # Dimensiones y hechos se publican juntos para no dejar una carga parcial.
        from scripts.create_analytic_views import create_views
        from scripts.refresh_dashboard import refresh
        create_views()
        refresh()
        return
    t0 = time.time()
    print("=" * 60)
    print("  PIPELINE DWH — Ecuador Seguridad Pública")
    print("=" * 60)

    if paso in ("todos", "dims"):
        # Las dimensiones se reconstruyen desde cero: si no se vacían, quedan
        # filas viejas (p. ej. provincia NULL de ENEMDU) que contaminan los joins.
        print("\n── RESET DWH ──")
        truncate_dwh()

        print("\n── DIMENSIONES ──")
        for nombre, fn in DIMENSIONES:
            fn()

    if paso in ("todos", "facts"):
        print("\n── HECHOS ──")
        for nombre, fn in HECHOS:
            fn()

    if paso in ("todos", "cubos"):
        print("\n── CUBOS OLAP ──")
        refresh_all_cubes()

    elapsed = time.time() - t0
    print(f"\nPipeline completado en {elapsed:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline DWH: dimensiones, hechos y cubos")
    parser.add_argument("paso", nargs="?", default="todos",
                        choices=("todos", "dims", "facts", "cubos"))
    parser.add_argument("--legacy", action="store_true", help="Ejecutar explícitamente el cargador histórico, incompatible con el nuevo contrato de clean")
    args = parser.parse_args()
    run(args.paso, legacy=args.legacy)
