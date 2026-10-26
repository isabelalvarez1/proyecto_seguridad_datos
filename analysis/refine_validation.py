"""Refinar fechas de una ejecución ya terminada, solo en clean_validacion.

Conserva tablas, filas y campos originales; reevalúa reportes con el código
actual y repite los controles de conservación. No reconstruye el DW.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import text

from analysis.run_clean_validation import (
    REPORT_ROOT, RUN_PATTERN, TARGET_SCHEMA, SOURCES, columns, profile,
    candidate_checks, numeric_summaries, frequencies, coverage, per_file_profile,
    operational_comparison, crossing_coverage, protected_snapshot, write_findings, numeric_histograms,
    write_csv, write_json, make_plots, log,
)
from analysis.validation_rules import TEMP_FUNCTIONS, derived_expressions, ident
from utils.config import engine, PROJECT_ROOT


def update_edg_dates(conn, table, derived):
    names = [name for name in derived if name in {
        'v_fecha_fall', 'v_fecha_insc', 'v_fecha_nac',
        'v_fecha_fall_estado', 'v_fecha_insc_estado', 'v_fecha_nac_estado'}]
    setters = ', '.join(f'{ident(name)}={derived[name]}' for name in names)
    conditions = ' OR '.join(f'(r.{ident(name)} IS NULL AND ({derived[name]}) IS NOT NULL)'
                             for name in names if not name.endswith('_estado'))
    # No escribir salvo en la tabla generada del esquema fijo de validación.
    return conn.execute(text(f'UPDATE {ident(TARGET_SCHEMA)}.{ident(table)} r '
                             f'SET {setters} WHERE {conditions}')).rowcount


def reanalyze(source, table, report_dir, previous, repaired_rows):
    target = f'{ident(TARGET_SCHEMA)}.{ident(table)}'
    directory = report_dir / source
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text("SET LOCAL statement_timeout='20min'"))
        conn.execute(text('SET LOCAL jit=off'))
        info = columns(conn, 'raw', source)
        originals = [item['column_name'] for item in info]
        derived = derived_expressions(source, originals)
        new_info = [item for item in columns(conn, TARGET_SCHEMA, table) if item['column_name'] in derived]
        count = conn.execute(text(f'SELECT count(*) FROM {target}')).scalar_one()
        original_record = 'ROW(' + ', '.join(ident(col) for col in originals) + ')::text'
        mismatches = conn.execute(text(f'SELECT count(*) FROM {target} WHERE md5({original_record}) <> _raw_hash')).scalar_one()
        if count != previous['rows_input'] or mismatches:
            raise AssertionError(f'Originales o filas alteradas en {target}')
        write_csv(directory / 'perfil_derivadas.csv', profile(conn, TARGET_SCHEMA, table, new_info, count))
        numeric = numeric_summaries(conn, target, derived)
        write_csv(directory / 'distribuciones_numericas.csv', numeric)
        numeric_histograms(conn, target, directory, numeric)
        cats = frequencies(conn, target, derived)
        write_csv(directory / 'frecuencias_derivadas.csv', cats)
        monthly = coverage(conn, target, source)
        write_csv(directory / 'cobertura_mensual.csv', monthly)
        by_file = per_file_profile(conn, target, derived, originals)
        write_json(directory / 'cobertura_por_archivo.json', by_file)
        checks = candidate_checks(source, derived)
        expressions = [f'count(*) FILTER (WHERE ({condition})) AS {ident(name)}' for name, condition in checks.items()]
        previous['checks'] = dict(conn.execute(text(f"SELECT {', '.join(expressions)} FROM {target}")).mappings().one())
        previous.update(derived_expressions=derived, numeric_summaries=numeric, coverage=monthly,
                        file_coverage=by_file, original_value_mismatches=mismatches,
                        status_counts=[row for row in cats if row['variable'].endswith('_estado')],
                        operational_clean_read_only_comparison=operational_comparison(conn, source),
                        refined_rows=repaired_rows)
    write_json(directory / 'resumen.json', previous)
    with (directory / 'perfil_raw.csv').open(encoding='utf-8-sig', newline='') as f:
        raw_profile = list(csv.DictReader(f))
    for row in raw_profile:
        row['pct_ausente_o_desconocido'] = float(row['pct_ausente_o_desconocido'])
    make_plots(directory, source, raw_profile, monthly, cats)
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not RUN_PATTERN.fullmatch(args.run_id):
        parser.error('Identificador inválido')
    report_dir = REPORT_ROOT / args.run_id
    manifest = json.loads((report_dir / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'COMPLETED':
        raise ValueError('Esperar a que termine la ejecución principal antes de refinar')
    completed = manifest['completed_sources']
    # Evita que un manifiesto manipulado dirija escrituras fuera de validación.
    expected = {source: f'{TARGET_SCHEMA}.{source}_{args.run_id}' for source in manifest['sources']}
    if completed != expected or any(source not in SOURCES for source in completed):
        raise ValueError('Destinos no corresponden a la ejecución')
    audit = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING',
             'source_hashes': {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
                               for name in ['analysis/validation_rules.py', 'analysis/refine_validation.py']}}
    write_json(report_dir / 'refinamiento.json', audit)
    before = json.loads((report_dir / 'protected_before.json').read_text(encoding='utf-8'))
    summaries = {}
    try:
        for source in completed:
            table = f'{source}_{args.run_id}'
            previous = json.loads((report_dir / source / 'resumen.json').read_text(encoding='utf-8'))
            repaired = 0
            if source == 'edg':
                log('Confirmando fechas de EDG con día, mes y año originales')
                with engine.connect() as conn, conn.begin():
                    conn.execute(text("SET LOCAL statement_timeout='20min'"))
                    conn.execute(text('SET LOCAL jit=off'))
                    conn.execute(text(TEMP_FUNCTIONS))
                    raw_columns = [item['column_name'] for item in columns(conn, 'raw', source)]
                    repaired = update_edg_dates(conn, table, derived_expressions(source, raw_columns))
                log(f'EDG: {repaired} filas con fechas adicionales confirmadas')
            # Actualizar comparación de todas las fuentes contra las tablas _1.
            if source == 'edg':
                summaries[source] = reanalyze(source, table, report_dir, previous, repaired)
            else:
                with engine.connect() as conn, conn.begin():
                    conn.execute(text('SET TRANSACTION READ ONLY'))
                    previous['operational_clean_read_only_comparison'] = operational_comparison(conn, source)
                    numeric_histograms(conn, f'{ident(TARGET_SCHEMA)}.{ident(table)}',
                                       report_dir / source, previous['numeric_summaries'])
                write_json(report_dir / source / 'resumen.json', previous)
                summaries[source] = previous
        crossings = crossing_coverage(summaries)
        write_json(report_dir / 'cobertura_provincia_anio.json', crossings)
        pairs = {name: {(r['anio'], r['provincia']) for r in rows
                        if r['anio'] is not None and r['provincia'] is not None}
                 for name, rows in crossings.items()}
        write_csv(report_dir / 'cruces_candidatos.csv', [
            {'fuente_a': a, 'fuente_b': b, 'pares_compartidos': len(pairs[a] & pairs[b])}
            for a in pairs for b in pairs if a < b])
        after = protected_snapshot()
        write_json(report_dir / 'protected_after_refinement.json', after)
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        conservation = {'status': 'UNCHANGED' if not changed else 'CHANGED_REQUIRES_REVIEW', 'changed_objects': changed}
        write_json(report_dir / 'conservacion_refinamiento.json', conservation)
        write_findings(report_dir, summaries, conservation)
        if changed:
            raise AssertionError(f'Cambios externos detectados: {changed}')
        audit['status'] = 'COMPLETED'
        audit['edg_refined_rows'] = summaries.get('edg', {}).get('refined_rows', 0)
        log('Refinamiento terminado; esquemas protegidos conservados')
    except BaseException as error:
        audit['status'] = 'FAILED'
        audit['error'] = str(error)
        raise
    finally:
        audit['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(report_dir / 'refinamiento.json', audit)


if __name__ == '__main__':
    main()
