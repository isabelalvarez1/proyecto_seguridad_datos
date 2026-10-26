"""Auditoría posterior, de solo lectura, de una publicación clean completada."""
import argparse
from datetime import datetime, timezone
import json
import re
import time

from sqlalchemy import text

from analysis.run_clean_validation import protected_snapshot, write_json, log
from scripts.run_clean import source_metrics
from utils.config import PROJECT_ROOT, engine
from utils.validation_sql import SOURCES, ident


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--wait-seconds', type=int, default=0,
                        help='Esperar una publicación activa antes de auditar; por defecto no espera')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9_]{1,25}', args.run_id):
        parser.error('Identificador inválido')
    directory = PROJECT_ROOT / 'reports' / 'clean' / args.run_id
    if args.wait_seconds < 0:
        parser.error('wait-seconds no puede ser negativo')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    deadline = time.monotonic() + args.wait_seconds
    last_log = 0
    while manifest['status'] == 'RUNNING' and time.monotonic() < deadline:
        if time.monotonic() - last_log >= 60:
            log('Publicación activa: esperando el control de conservación y la confirmación final')
            last_log = time.monotonic()
        time.sleep(5)
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'PUBLISHED':
        raise ValueError('Esperar a que termine la publicación')
    expected_names = {source: 'clean.' + target for source, target in SOURCES.items()}
    if manifest['published_sources'] != expected_names:
        raise ValueError('El manifiesto no corresponde al contrato de publicación')
    baseline = json.loads((directory / 'protected_before.json').read_text(encoding='utf-8'))
    summaries = {source: json.loads((directory / source / 'resumen.json').read_text(encoding='utf-8'))
                 for source in SOURCES}
    metrics = {}
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text('SET LOCAL jit=off'))
        for source, table in SOURCES.items():
            qualified = f'clean.{ident(table)}'
            current = source_metrics(conn, qualified, source)
            if current != summaries[source]['metrics']:
                raise AssertionError(f'Métricas distintas después de publicar: {table}')
            foreign_run = conn.execute(text(f'SELECT count(*) FROM {qualified} WHERE _clean_run_id IS DISTINCT FROM :run'),
                                       {'run': args.run_id}).scalar_one()
            if foreign_run:
                raise AssertionError(f'Filas de otra ejecución en {table}')
            metrics[source] = current
            log(f'Publicación comprobada: clean.{table}, {current["rows"]:,} registros')
    keys = {key for key in baseline if key.split('.')[0] in ('raw', 'dwh', 'catalogo')}
    actual = protected_snapshot(only_keys=keys)
    changed = sorted(key for key in keys if actual.get(key) != baseline[key])
    result = {'run_id': args.run_id, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'status': 'UNCHANGED' if not changed else 'CHANGED_REQUIRES_REVIEW',
              'content_checked_schemas': ['raw', 'dwh', 'catalogo'],
              'changed_objects': changed, 'published_metrics': metrics}
    write_json(directory / 'postpublication_audit.json', result)
    if changed:
        raise AssertionError(f'Cambios en esquemas protegidos: {changed}')
    log('Auditoría posterior completada: publicación correcta; raw, DW y catálogo sin cambios')


if __name__ == '__main__':
    main()
