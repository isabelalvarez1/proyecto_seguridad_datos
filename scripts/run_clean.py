"""Construir y publicar clean desde una validación aprobada, sin ejecutar DW.

python -m scripts.run_clean --validation-run validacion_20261016_01 --publish
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import traceback

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from analysis.run_clean_validation import columns, protected_snapshot, write_json, write_csv, log
from utils.clean_projection import clean_projection
from utils.validation_sql import SOURCES, ident, literal, norm
from utils.config import PROJECT_ROOT, engine


STAGING_SCHEMA = 'clean_preparacion'
OUTPUT_SCHEMA = 'clean'
HISTORY_SCHEMA = 'clean_historial'
RUN_PATTERN = re.compile(r'^[a-z0-9_]{1,25}$')


def load_validation(run_id):
    if not RUN_PATTERN.fullmatch(run_id):
        raise ValueError('Identificador de validación inválido')
    directory = PROJECT_ROOT / 'reports' / 'eda' / run_id
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'COMPLETED':
        raise ValueError('La validación no terminó correctamente')
    expected = {source: f'clean_validacion.{source}_{run_id}' for source in SOURCES}
    if manifest['completed_sources'] != expected:
        raise ValueError('Se requieren las cinco fuentes validadas con destinos conocidos')
    refined = directory / 'refinamiento.json'
    if refined.exists() and json.loads(refined.read_text(encoding='utf-8'))['status'] != 'COMPLETED':
        raise ValueError('El refinamiento de validación no terminó')
    conservation = directory / ('conservacion_refinamiento.json' if refined.exists() else 'conservacion.json')
    if json.loads(conservation.read_text(encoding='utf-8'))['status'] != 'UNCHANGED':
        raise ValueError('La validación detectó cambios en fuentes protegidas')
    return manifest


def projection_sql(input_table, raw_info, expressions, run_id, predicate='TRUE'):
    cache = {}
    rewritten = dict(expressions)
    for info in raw_info:
        column = info['column_name']
        references = ['r.' + ident(column)]
        if re.fullmatch(r'[a-z_][a-z0-9_]*', column):
            references.append('r.' + column)
        for reference in references:
            expression = norm(reference)
            if any(expression in value for value in rewritten.values()):
                name = f'_clean_cache_{len(cache)}'
                cache[name] = expression
                rewritten = {key: value.replace(expression, 'r.' + ident(name)) for key, value in rewritten.items()}
    extras = ', ' + ', '.join(value + ' AS ' + ident(key) for key, value in cache.items()) if cache else ''
    output = ', '.join(value + ' AS ' + ident(key) for key, value in rewritten.items())
    schema, table = input_table.split('.')
    return f"""
        WITH normalized AS MATERIALIZED (
            SELECT r.* {extras} FROM {ident(schema)}.{ident(table)} r WHERE {predicate}
        )
        SELECT {output}, {literal(run_id)}::text AS _clean_run_id FROM normalized r
    """


def verify_source(conn, source, input_table, raw_info):
    schema, table = input_table.split('.')
    available = {item['column_name']: item['data_type'] for item in columns(conn, schema, table)}
    for item in raw_info:
        if available.get(item['column_name']) != item['data_type']:
            raise ValueError(f'Original distinto o ausente: {source}.{item["column_name"]}')
    required = {'_validation_run_id', '_raw_ctid', '_raw_hash'}
    if not required <= available.keys():
        raise ValueError(f'Falta procedencia en {input_table}')
    return available


def build_source(source, validation, run_id, baseline, directory):
    input_table = validation['completed_sources'][source]
    output_table = SOURCES[source] + '_' + run_id
    target = f'{ident(STAGING_SCHEMA)}.{ident(output_table)}'
    source_dir = directory / source
    source_dir.mkdir()
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
        conn.execute(text("SET LOCAL statement_timeout='20min'"))
        conn.execute(text('SET LOCAL jit=off'))
        conn.execute(text("SET LOCAL work_mem='64MB'"))
        raw_info = columns(conn, 'raw', source)
        available = verify_source(conn, source, input_table, raw_info)
        expressions, audit = clean_projection(source, raw_info, available)
        if len(output_table) > 63:
            raise ValueError('Nombre de tabla demasiado largo')
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {ident(STAGING_SCHEMA)}'))
        query = projection_sql(input_table, raw_info, expressions, run_id, 'FALSE')
        conn.execute(text(f'CREATE TABLE {target} AS {query}'))
        pages = conn.execute(text("SELECT ceil(pg_relation_size(to_regclass(:t))::numeric/current_setting('block_size')::integer)::bigint"),
                             {'t': input_table}).scalar_one()
        for start in range(0, pages, 4000):
            end = min(start + 4000, pages)
            predicate = f"r.ctid >= '({start},0)'::tid AND r.ctid < '({end},0)'::tid"
            query = projection_sql(input_table, raw_info, expressions, run_id, predicate)
            inserted = conn.execute(text(f'INSERT INTO {target} {query}')).rowcount
            log(f'{source}: páginas {start}-{end}/{pages}, {inserted:,} filas')
        # Reconstruir el registro de origen desde columnas originales conservadas.
        original_fields = [ident(item['clean_column'] + '_original' if item['original_preserved'] else item['clean_column'])
                           for item in audit]
        original_record = 'ROW(' + ', '.join(original_fields) + ')::text'
        control = dict(conn.execute(text(f"""
            SELECT count(*) rows,
                   count(*) FILTER(WHERE md5({original_record}) <> _raw_hash) original_mismatches,
                   COALESCE(sum(hashtextextended({original_record},0)::numeric),0)::text hash_sum_0,
                   COALESCE(sum(hashtextextended({original_record},1)::numeric),0)::text hash_sum_1
            FROM {target}
        """)).mappings().one())
        expected = baseline['raw.' + source]
        for field in ('rows', 'hash_sum_0', 'hash_sum_1'):
            if control[field] != expected[field]:
                raise AssertionError(f'{source}: contenido original difiere de raw ({field})')
        if control['original_mismatches']:
            raise AssertionError(f'{source}: originales de validación alterados')
        metrics = source_metrics(conn, target, source)
        source_q = '.'.join(ident(part) for part in input_table.split('.'))
        critical = ['periodo'] if source == 'enemdu' else [item['column_name'] for item in raw_info if item['column_name'].startswith('fecha_')]
        for field in critical:
            old = conn.execute(text(f'SELECT count({ident("v_"+field)}) FROM {source_q}')).scalar_one()
            new = conn.execute(text(f'SELECT count({ident(field)}) FROM {target}')).scalar_one()
            if old != new:
                raise AssertionError(f'Pérdida en {source}.{field}: {old} -> {new}')
        if source == 'enemdu' and metrics['factor_no_positivo']:
            raise AssertionError('ENEMDU contiene factores no positivos: requiere revisión')
        duplicate = dict(conn.execute(text(f"""
            SELECT count(*) grupos,COALESCE(sum(n-1),0) filas_adicionales
            FROM (SELECT count(*) n FROM {target} GROUP BY _raw_hash HAVING count(*)>1) q
        """)).mappings().one())
        statuses = []
        for field in expressions:
            if field.endswith('_estado'):
                statuses.extend({'variable': field, **dict(row)} for row in conn.execute(text(
                    f'SELECT {ident(field)} categoria,count(*) registros FROM {target} GROUP BY 1 ORDER BY 2 DESC'
                )).mappings())
        date = {'mdi_homicidio': 'fecha_infraccion', 'mdi_arma': 'fecha_evento',
                'mdi_desaparecido': 'fecha_desaparicion', 'edg': 'fecha_fall'}.get(source)
        year = 'anio' if source == 'enemdu' else f'extract(year from {ident(date)})::integer'
        coverage = [dict(row) for row in conn.execute(text(
            f'SELECT {year} anio,count(*) registros FROM {target} GROUP BY 1 ORDER BY 1 NULLS LAST'
        )).mappings()]
        comment = f'Clean {run_id}; fuente raw.{source}; validación {validation["run_id"]}; sin deduplicación ni imputación.'
        conn.execute(text(f'COMMENT ON TABLE {target} IS {literal(comment)}'))
        summary = {'source': 'raw.' + source, 'validation': input_table, 'staged_table': f'{STAGING_SCHEMA}.{output_table}',
                   'canonical_table': 'clean.' + SOURCES[source], 'controls': control, 'metrics': metrics,
                   'duplicates_retained': duplicate, 'coverage': coverage, 'states': statuses,
                   'column_count': len(expressions) + 1, 'column_mapping': audit}
        write_json(source_dir / 'resumen.json', summary)
        write_csv(source_dir / 'mapeo_columnas.csv', audit)
        write_csv(source_dir / 'estados.csv', statuses)
        write_csv(source_dir / 'cobertura_anual.csv', coverage)
    log(f'{source}: salida comprobada ({control["rows"]:,} filas, originales conservados)')
    return summary


def source_metrics(conn, target, source):
    expressions = {'rows': 'count(*)'}
    if source == 'enemdu':
        expressions.update(periodos_validos='count(periodo)', periodos_ausentes='count(*)-count(periodo)',
                           edad_abierta_98_mas='count(*) FILTER(WHERE edad_censurada)',
                           edad_no_informa="count(*) FILTER(WHERE p03_estado='UNKNOWN')",
                           ingreso_respuesta_no_numerica="count(*) FILTER(WHERE ingrl_estado='NON_NUMERIC_RESPONSE')",
                           ingreso_no_informa="count(*) FILTER(WHERE ingrl_estado='UNKNOWN')",
                           factor_no_positivo='count(*) FILTER(WHERE fexp<=0)',
                           dpa_ambiguo="count(*) FILTER(WHERE dpa_estado='AMBIGUOUS')",
                           dpa_sin_correspondencia="count(*) FILTER(WHERE dpa_estado='NOT_FOUND')")
    elif source == 'edg':
        expressions.update(fechas_fallecimiento_validas='count(fecha_fall)',
                           nacimiento_posterior_fallecimiento='count(*) FILTER(WHERE fecha_nac_posterior_fall)')
    if source in ('mdi_homicidio', 'mdi_arma', 'mdi_desaparecido'):
        expressions.update(coordenadas_observadas="count(*) FILTER(WHERE geo_estado='OBSERVED_NOT_IMPUTED')",
                           coordenadas_cero_retiradas="count(*) FILTER(WHERE geo_estado='ZERO_PAIR')")
    if source == 'mdi_arma':
        expressions['cantidad_no_informada'] = 'count(*)-count(cantidad)'
    sql = ', '.join(value + ' AS ' + ident(key) for key, value in expressions.items())
    return dict(conn.execute(text(f'SELECT {sql} FROM {target}')).mappings().one())


def relation_info(conn, schema, table):
    return conn.execute(text('SELECT c.oid::bigint oid,c.relkind kind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
                            'WHERE n.nspname=:s AND c.relname=:t'), {'s': schema, 't': table}).mappings().first()


def cleanup_staging_schema(conn):
    """Eliminar preparación solo vacía; RESTRICT conserva objetos pendientes."""
    try:
        # El savepoint permite conservar la publicación si hay otras tablas,
        # funciones o tipos pendientes en el esquema (incluidas otras cargas).
        with conn.begin_nested():
            conn.execute(text("SET LOCAL lock_timeout='10s'"))
            conn.execute(text(f'DROP SCHEMA IF EXISTS {ident(STAGING_SCHEMA)} RESTRICT'))
    except DBAPIError as error:
        if getattr(error.orig, 'pgcode', None) != '2BP01':
            raise
        return 'KEPT_NOT_EMPTY'
    return 'REMOVED_OR_ALREADY_ABSENT'


def publish(summaries, run_id, baseline):
    from utils.analytic_views import OWNER_TAG, SCHEMA as ANALYTIC_SCHEMA, definitions
    from scripts.create_analytic_views import bind_views
    backups = []
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'proyecto_ecuador_clean_publication'})
        conn.execute(text("SET LOCAL lock_timeout='10s'"))
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS clean'))
        for source, item in summaries.items():
            canonical = SOURCES[source]
            existing = relation_info(conn, OUTPUT_SCHEMA, canonical)
            if existing:
                key = f'clean.{canonical}'
                if key not in baseline or existing['oid'] != baseline[key]['oid'] or existing['kind'] != 'r':
                    raise ValueError(f'Destino cambió o no es tabla: {key}')
                dependencies = conn.execute(text("""SELECT DISTINCT n.nspname schema,v.relname name,
                    v.relkind kind,obj_description(v.oid,'pg_class') comment
                    FROM pg_depend d JOIN pg_rewrite rw ON rw.oid=d.objid
                    JOIN pg_class v ON v.oid=rw.ev_class JOIN pg_namespace n ON n.oid=v.relnamespace
                    WHERE d.refobjid=:oid AND rw.ev_class<>:oid"""), {'oid': existing['oid']}).mappings().all()
                for dependency in dependencies:
                    if (dependency['schema'] != ANALYTIC_SCHEMA or dependency['name'] not in definitions()
                            or dependency['kind'] != 'v' or dependency['comment'] != OWNER_TAG):
                        raise ValueError(f'{key} tiene dependencia no administrada: {dependency["schema"]}.{dependency["name"]}')
                backup = canonical + '_' + run_id
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {ident(HISTORY_SCHEMA)}'))
                if relation_info(conn, HISTORY_SCHEMA, backup):
                    raise ValueError(f'Ya existe el respaldo {backup}')
                conn.execute(text(f'ALTER TABLE clean.{ident(canonical)} RENAME TO {ident(backup)}'))
                conn.execute(text(f'ALTER TABLE clean.{ident(backup)} SET SCHEMA {ident(HISTORY_SCHEMA)}'))
                backups.append({'before': key, 'after': f'{HISTORY_SCHEMA}.{backup}', 'oid': existing['oid']})
            stage_name = item['staged_table'].split('.')[1]
            conn.execute(text(f'LOCK TABLE {ident(STAGING_SCHEMA)}.{ident(stage_name)} IN ACCESS EXCLUSIVE MODE'))
            count = conn.execute(text(f'SELECT count(*) FROM {ident(STAGING_SCHEMA)}.{ident(stage_name)}')).scalar_one()
            if count != item['controls']['rows']:
                raise AssertionError(f'El staging cambió: {stage_name}')
            conn.execute(text(f'ALTER TABLE {ident(STAGING_SCHEMA)}.{ident(stage_name)} RENAME TO {ident(canonical)}'))
            conn.execute(text(f'ALTER TABLE {ident(STAGING_SCHEMA)}.{ident(canonical)} SET SCHEMA clean'))
        # Conserva los OID de las vistas; sus dependientes leen el nuevo clean,
        # no las tablas archivadas. Si cambia el contrato, se revierte todo.
        bind_views(conn)
        log('Vistas analíticas reenlazadas al nuevo clean dentro de la publicación.')
    return backups


def write_summary(directory, manifest, summaries, conservation):
    lines = ['# Publicación de clean', '', f"Ejecución: `{manifest['run_id']}`.",
             f"Validación de origen: `{manifest['validation_run']}`.", '',
             f"Estado: **{manifest['status']}**. Conservación de objetos previos: **{conservation['status']}**.", '',
             f"Limpieza de preparación: **{manifest.get('staging_cleanup', 'NOT_RUN')}**.", '',
             '| Fuente | Tabla clean | Filas | Originales alterados |', '|---|---|---:|---:|']
    for source, item in summaries.items():
        lines.append(f"| {source} | `{item['canonical_table']}` | {item['controls']['rows']} | {item['controls']['original_mismatches']} |")
    for source, item in summaries.items():
        lines.extend(['', f'## {source}', ''])
        lines.extend(f'- {key}: {value}.' for key, value in item['metrics'].items())
    lines.extend(['', '## Alcance y pendientes', '',
                  '- Se mantienen los candidatos a duplicados y los códigos pendientes de diccionario.',
                  '- Las cantidades no informadas no se convierten en cero ni uno.',
                  '- Edad «98 y más» se conserva como categoría abierta, no como edad exacta.',
                  '- Las respuestas de ingreso no numéricas se conservan y clasifican por separado.',
                  '- Las coordenadas (0,0), fuera de rango global o con par incompleto no se usan como coordenadas limpias.',
                  '- No se imputan coordenadas ni se resuelven DPA ambiguos arbitrariamente.',
                  '- No se calculan estimaciones oficiales ENEMDU ni asociaciones causales.',
                  '- No se ejecutaron cargas del DW, refrescos de cubos, entrenamiento de modelos ni cambios de API/dashboard.',
                  '- El DW existente conserva sus resultados anteriores y requiere una fase separada de adaptación.', ''])
    (directory / 'resultado.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-run', required=True)
    parser.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('clean_%Y%m%d_%H%M%S'))
    parser.add_argument('--publish', action='store_true', help='Publicar clean tras verificar las cinco tablas')
    parser.add_argument('--plan', action='store_true', help='Mostrar destinos sin escribir en la base')
    args = parser.parse_args()
    if not RUN_PATTERN.fullmatch(args.run_id):
        parser.error('run-id inválido')
    validation = load_validation(args.validation_run)
    if args.plan:
        for source, target in SOURCES.items():
            print(f'{validation["completed_sources"][source]} -> {STAGING_SCHEMA}.{target}_{args.run_id} -> clean.{target}')
        return
    root = PROJECT_ROOT / 'reports' / 'clean'
    root.mkdir(parents=True, exist_ok=True)
    directory = root / args.run_id
    directory.mkdir(exist_ok=False)
    manifest = {'run_id': args.run_id, 'validation_run': args.validation_run, 'status': 'RUNNING',
                'started_at': datetime.now(timezone.utc).isoformat(), 'publish_requested': args.publish,
                'source_hashes': {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
                                  for name in ['scripts/run_clean.py', 'utils/clean_projection.py', 'utils/validation_sql.py']}}
    write_json(directory / 'manifest.json', manifest)
    summaries = {}
    try:
        log('Registrando referencias actuales; no se actualizarán DW ni cubos')
        baseline = protected_snapshot()
        write_json(directory / 'protected_before.json', baseline)
        for source in SOURCES:
            log(f'Construyendo {source} en {STAGING_SCHEMA}')
            summaries[source] = build_source(source, validation, args.run_id, baseline, directory)
            manifest['built_sources'] = {key: value['staged_table'] for key, value in summaries.items()}
            write_json(directory / 'manifest.json', manifest)
        after_build = protected_snapshot(only_keys=set(baseline))
        changed = sorted(key for key in baseline if baseline[key] != after_build.get(key))
        write_json(directory / 'protected_after_build.json', after_build)
        if changed:
            raise AssertionError(f'Cambios externos en objetos protegidos: {changed}')
        backups = publish(summaries, args.run_id, baseline) if args.publish else []
        manifest['backups'] = backups
        manifest['status'] = 'PUBLISHED' if args.publish else 'BUILT_AND_VERIFIED'
        # OID, tamaño/conteo y definiciones anteriores fueron verificados antes
        # del intercambio. Después se comprueba identidad de objetos ajenos.
        with engine.connect() as conn, conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            identities = {}
            moved = {item['before']: item['after'] for item in backups}
            for key, previous in baseline.items():
                current_key = moved.get(key, key)
                schema, table = current_key.split('.')
                current = relation_info(conn, schema, table)
                if current is None or current['oid'] != previous['oid']:
                    raise AssertionError(f'Objeto previo perdido o reemplazado: {key}')
                identities[key] = {'current_name': current_key, 'oid': current['oid']}
            published = {}
            if args.publish:
                for source, target in SOURCES.items():
                    published[source] = dict(relation_info(conn, 'clean', target))
        conservation = {'status': 'UNCHANGED', 'content_verified_before_atomic_publication': True,
                        'original_objects_after_publication': identities}
        write_json(directory / 'conservacion.json', conservation)
        manifest['published_sources'] = {key: 'clean.' + value for key, value in SOURCES.items()} if args.publish else {}
        if args.publish:
            with engine.begin() as conn:
                manifest['staging_cleanup'] = cleanup_staging_schema(conn)
            log(f"Limpieza de {STAGING_SCHEMA}: {manifest['staging_cleanup']}")
        else:
            manifest['staging_cleanup'] = 'KEPT_NOT_PUBLISHED'
        write_summary(directory, manifest, summaries, conservation)
        log(f'Terminado: {manifest["status"]}. Reporte: {directory / "resultado.md"}')
    except BaseException as error:
        manifest['status'] = 'FAILED'
        manifest['error'] = str(error)
        (directory / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(directory / 'manifest.json', manifest)


if __name__ == '__main__':
    main()
