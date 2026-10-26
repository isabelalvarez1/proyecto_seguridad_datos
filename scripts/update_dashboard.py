"""Flujo único: validación opcional -> clean opcional -> mart web atómico.

Sin opciones solo refresca el mart desde clean actual.
"""
import argparse
from datetime import datetime, timezone
import subprocess
import sys
import uuid

from utils.config import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--from-raw', action='store_true', help='Validar raw actual y publicar clean con las reglas vigentes')
    group.add_argument('--validation-run', help='Publicar clean a partir de una validación ya revisada')
    args = parser.parse_args()
    suffix = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:4]

    def run(module, *extra):
        subprocess.run([sys.executable, '-u', '-m', module, *extra], cwd=PROJECT_ROOT, check=True)

    validation = args.validation_run
    if args.from_raw:
        validation = 'v_' + suffix
        run('analysis.run_clean_validation', '--run-id', validation)
    if validation:
        run('scripts.run_clean', '--validation-run', validation, '--run-id', 'c_' + suffix, '--publish')
    # Para un clean preexistente, asegurar la definición vigente antes de agregar.
    from scripts.create_analytic_views import create_views
    from scripts.refresh_dashboard import refresh
    create_views()
    refresh()
    print('Dashboard actualizado. La evaluación predictiva conserva su versión y fecha de estudio.')


if __name__ == '__main__':
    main()
