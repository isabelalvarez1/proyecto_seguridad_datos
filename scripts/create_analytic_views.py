"""Vistas normales y matriz de selección sobre clean. No recarga ni modifica datos.

python -m scripts.create_analytic_views --plan
python -m scripts.create_analytic_views
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import traceback

from sqlalchemy import text

from analysis.run_clean_validation import columns, write_json, write_csv, log
from utils.analytic_views import SCHEMA, OWNER_TAG, VIEWS, definitions
from utils.config import engine, PROJECT_ROOT
from utils.validation_sql import ident, literal


def snapshot_existing():
    """Estructura, identidades, conteos y contadores DML; no son hashes de contenido."""
    result = {}
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text('SET LOCAL jit=off'))
        rows = conn.execute(text("""
            SELECT n.nspname schema,c.relname name,c.relkind kind,c.oid::bigint oid,
                   c.relfilenode::bigint filenode,
                   COALESCE(s.n_tup_ins,0) inserted,COALESCE(s.n_tup_upd,0) updated,
                   COALESCE(s.n_tup_del,0) deleted
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid
            WHERE n.nspname IN ('raw','clean','dwh','catalogo') AND c.relkind IN ('r','p','v','m')
            ORDER BY 1,2
        """)).mappings().all()
        for item in rows:
            item = dict(item)
            key = f'{item["schema"]}.{item["name"]}'
            log(f'Control de estructura/conteo: {key}')
            item['columns'] = [dict(value) for value in columns(conn, item['schema'], item['name'])]
            if item['kind'] in ('r', 'p', 'm'):
                item['rows'] = conn.execute(text(f'SELECT count(*) FROM {ident(item["schema"])}.{ident(item["name"])}')).scalar_one()
            if item['kind'] in ('v', 'm'):
                item['definition'] = conn.execute(text('SELECT pg_get_viewdef(:oid,true)'), {'oid': item['oid']}).scalar_one()
            result[key] = item
    return result


def check_contract(conn):
    for view in VIEWS:
        present = {item['column_name'] for item in columns(conn, 'clean', view.table)}
        missing = view.required - present
        if missing:
            raise ValueError(f'Faltan columnas en clean.{view.table}: {sorted(missing)}')
        names = [field.name for field in view.fields]
        if len(names) != len(set(names)):
            raise ValueError(f'Contrato con alias repetidos: {view.name}')


def bind_views(conn):
    """Reenlazar vistas administradas en la misma transacción que publica clean."""
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'proyecto_ecuador_analytic_views'})
    check_contract(conn)
    for name in definitions():
        existing = conn.execute(text("""
                SELECT c.relkind,obj_description(c.oid,'pg_class') comment
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=:schema AND c.relname=:name
            """), {'schema': SCHEMA, 'name': name}).mappings().first()
        if existing and (existing['relkind'] != 'v' or existing['comment'] != OWNER_TAG):
            raise ValueError(f'{SCHEMA}.{name} existe y no pertenece a este contrato; no se reemplaza')
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {ident(SCHEMA)}'))
    for name, query in definitions().items():
        conn.execute(text(f'CREATE OR REPLACE VIEW {ident(SCHEMA)}.{ident(name)} AS {query}'))
        conn.execute(text(f'COMMENT ON VIEW {ident(SCHEMA)}.{ident(name)} IS {literal(OWNER_TAG)}'))


def create_views():
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout='10s'"))
        bind_views(conn)
    log('Seis vistas analíticas enlazadas a clean.')


def excluded_reason(column, populated, total):
    if populated == 0:
        return 'EXCLUIDA_SIN_VALORES', 'Sin valores observados en esta versión; no se imputa para fabricar información.'
    if column.endswith('_original') or column.startswith('_raw_') or column.startswith('_validation_'):
        return 'SOLO_AUDITORIA', 'Se conserva en clean para trazabilidad, no como variable de estudio.'
    if column.startswith('numeracion') or column in {'id_persona', 'id_hogar', 'id_vivienda', 'hogar', 'vivienda', 'p01', 'ced01a'}:
        return 'IDENTIFICACION_NO_PREDICTOR', 'Identificador/administración: no representa una característica sustantiva para los análisis candidatos.'
    if column in {'p03', 'mes'}:
        return 'REEMPLAZADA_POR_DERIVADA', 'La vista usa edad_anios o mes derivado del período validado; no duplica la representación de la misma información.'
    if re.fullmatch(r'(anio|mes|dia)_(fall|insc|nac)', column):
        return 'PARTES_FECHA_AUDITORIA', 'Partes de fecha conservadas para comprobar la conversión; la vista utiliza fechas y componentes derivados de ellas.'
    if column in {'causa103', 'causa67a', 'causa67b', 'causa80'}:
        return 'AGRUPACION_ALTERNATIVA', 'Se seleccionaron causa y causa4; otras clasificaciones se reservan para preguntas específicas y revisión de diccionario.'
    if column == 'fecha_nac':
        return 'NO_NECESARIA_CON_EDAD_REPORTADA', 'Se selecciona edad con unidad y señal de incoherencia cronológica; no se expone fecha exacta de nacimiento sin necesidad analítica.'
    if column == 'instruccion' and populated / max(total, 1) < 0.5:
        return 'COBERTURA_LIMITADA_ANALISIS_PRINCIPAL', 'Educación tiene cobertura insuficiente para describir el conjunto sin sesgo no evaluado; puede revisarse por subgrupo.'
    if column == 'calibre':
        return 'PENDIENTE_NORMALIZACION_UNIDAD', 'Requiere homologación de formatos/unidades; no es necesario para los análisis territoriales iniciales.'
    if column in {'latitud', 'longitud', 'coordenada_x', 'coordenada_y'} or column.startswith(('latitud_', 'longitud_', 'geo_')):
        return 'EXCLUIDA_DEL_ALCANCE_ACTUAL', 'Se prioriza territorio administrativo; localización puntual incompleta y sin objetivo espacial aprobado.'
    if column in {'mor_mat', 'muj_fertil'}:
        return 'UNIVERSO_ESPECIFICO', 'Variable de aplicación específica; no excluir por nulos globales, evaluar en un estudio de ese universo.'
    if column in {'status', 'motivacion', 'motivo_desaparicion', 'motivacion_observada', 'motivacion_desaparicion_observada'}:
        return 'PENDIENTE_COMPARABILIDAD', 'Cambios entre archivos/categorías; no mezclar equivalencias sin diccionario.'
    if column in {'sector', 'condactn', 'plan_muestreo', 'id_sector', 'zona'}:
        return 'PENDIENTE_DICCIONARIO_COBERTURA', 'No confundir códigos de sector/zona con rama de actividad; revisar su versión y universo.'
    if column.endswith('_estado'):
        return 'CONTROL_NO_PUBLICADO', 'Permanece en clean; la vista incluye los controles necesarios, sin implicar que el campo base esté excluido.'
    if populated / max(total, 1) < 0.1:
        return 'COBERTURA_LIMITADA_REVISAR_UNIVERSO', 'Menos del 10% informado globalmente; no implica inutilidad en un subgrupo. No eliminar de clean.'
    return 'NO_SELECCIONADA_EN_ALCANCE_INICIAL', 'Conservada en clean; requiere una pregunta y diccionario antes de ampliar la selección.'


def source_selection(conn, view, directory, expected):
    info = columns(conn, 'clean', view.table)
    fields = [item['column_name'] for item in info]
    values = conn.execute(text('SELECT ' + ','.join(f'count({ident(field)})' for field in fields) +
                               f' FROM clean.{ident(view.table)}')).one()
    by_input = {}
    for field in view.fields:
        for column in field.inputs:
            by_input.setdefault(column, []).append(field)
    selection = []
    for item, populated in zip(info, values):
        column = item['column_name']
        selected = by_input.get(column, [])
        if selected:
            decision = 'INCLUIDA_' + '_'.join(sorted({field.role.upper() for field in selected}))
            reason = ' | '.join(dict.fromkeys(field.description for field in selected))
        else:
            decision, reason = excluded_reason(column, populated, expected)
        selection.append({'tabla_clean': view.table, 'variable_clean': column, 'tipo': item['data_type'],
                          'registros': expected, 'con_valor': populated, 'null_sql': expected - populated,
                          'pct_null_sql': round((expected - populated) * 100 / max(expected, 1), 4),
                          'decision': decision, 'motivo': reason,
                          'campos_vista': ', '.join(field.name for field in selected)})
    write_csv(directory / 'seleccion_variables.csv', selection)
    return selection


def view_profile(conn, view, directory, expected):
    qualified = f'{ident(SCHEMA)}.{ident(view.name)}'
    count = conn.execute(text(f'SELECT count(*) FROM {qualified}')).scalar_one()
    if count != expected:
        raise AssertionError(f'{view.name}: cambió el número de filas {expected} -> {count}')
    info = {item['column_name']: item['data_type'] for item in columns(conn, SCHEMA, view.name)}
    expressions = []
    for field in view.fields:
        q = ident(field.name)
        expressions.append(f'count({q})')
        expressions.append(f'count(DISTINCT {q})' if info[field.name] == 'text' else 'NULL::bigint')
    values = conn.execute(text(f'SELECT {",".join(expressions)} FROM {qualified}')).one()
    profile = []
    for i, field in enumerate(view.fields):
        valid, distinct = values[i * 2:i * 2 + 2]
        profile.append({'variable': field.name, 'tipo': info[field.name], 'rol': field.role,
                        'registros': count, 'con_valor': valid, 'null_sql': count - valid,
                        'pct_null_sql': round((count - valid) * 100 / max(count, 1), 4),
                        'categorias_texto_distintas': distinct,
                        'descripcion': field.description, 'tratamiento_faltantes': field.missing})
    write_csv(directory / 'diccionario_vista.csv', profile)
    return {'rows': count, 'columns': len(view.fields), 'profile': profile}


def deterministic_checks(conn):
    result = {}
    catalog = conn.execute(text(f"""
        SELECT count(*) n,count(DISTINCT codigo_provincia) unique_codes
        FROM {SCHEMA}.v_catalogo_provincias
    """)).one()
    if catalog.n != 24 or catalog.unique_codes != 24:
        raise AssertionError('El catálogo provincial no tiene 24 correspondencias únicas: revisar fuente')
    result['catalog_provinces'] = catalog.n
    result['desapariciones'] = dict(conn.execute(text(f"""
        SELECT count(*) FILTER(WHERE duracion_origen='CALCULADA_FECHAS') recuperadas_por_fechas,
               count(*) FILTER(WHERE duracion_origen='DISCREPANCIA_REVISAR') discrepancias,
               count(*) FILTER(WHERE dias_hasta_localizacion<0) negativas,
               count(*) FILTER(WHERE dias_hasta_localizacion IS NOT NULL AND fecha_localizacion IS NULL) duraciones_sin_fecha
        FROM {SCHEMA}.v_desapariciones
    """)).mappings().one())
    if result['desapariciones']['negativas'] or result['desapariciones']['duraciones_sin_fecha']:
        raise AssertionError('Duraciones inválidas')
    result['enemdu'] = dict(conn.execute(text(f"""
        SELECT count(*) FILTER(WHERE provincia_origen='CATALOGO_PROVINCIAL_UNICO') provincias_recuperadas,
               count(*) FILTER(WHERE provincia IS NULL) provincia_pendiente,
               count(*) FILTER(WHERE dpa_estado='AMBIGUOUS' AND canton IS NOT NULL) canton_ambiguo_asignado,
               count(*) FILTER(WHERE edad_censurada AND edad_anios IS NOT NULL) edades_abiertas_convertidas_en_exactas,
               count(*) FILTER(WHERE pobreza IS NULL AND pobreza_binaria IS NOT NULL) pobreza_ausente_convertida,
               count(*) FILTER(WHERE ingrl_estado IN ('UNKNOWN','NON_NUMERIC_RESPONSE') AND ingreso_laboral IS NOT NULL) respuestas_ingreso_convertidas
        FROM {SCHEMA}.v_enemdu
    """)).mappings().one())
    for key in ('canton_ambiguo_asignado', 'edades_abiertas_convertidas_en_exactas',
                'pobreza_ausente_convertida', 'respuestas_ingreso_convertidas'):
        if result['enemdu'][key]:
            raise AssertionError(f'Conversión no permitida: {key}')
    result['defunciones'] = dict(conn.execute(text(f"""
        SELECT count(*) FILTER(WHERE grupo_edad='MENOR_DE_1_AÑO') menores_unidad_conocida,
               count(*) FILTER(WHERE edad_unidad IN ('DÍAS','DIAS','MESES','HORAS') AND edad_anios IS NOT NULL) unidades_mezcladas,
               count(*) FILTER(WHERE autopsia_codigo_pendiente AND autopsia_interpretada IS NOT NULL) codigos_autopsia_adivinados
        FROM {SCHEMA}.v_defunciones
    """)).mappings().one())
    if result['defunciones']['unidades_mezcladas'] or result['defunciones']['codigos_autopsia_adivinados']:
        raise AssertionError('Conversión demográfica no permitida')
    return result


def write_report(directory, results, checks, conservation):
    lines = ['# Vistas analíticas normales', '', f'Esquema: `{SCHEMA}`.', '',
             '| Vista | Registros conservados | Campos |', '|---|---:|---:|']
    for view in VIEWS:
        item = results[view.name]
        lines.append(f'| `{SCHEMA}.{view.name}` | {item["rows"]} | {item["columns"]} |')
    lines.extend(['', '## Recuperaciones sin imputación estadística', '',
                  f"- Duraciones derivadas de fechas observadas: {checks['desapariciones']['recuperadas_por_fechas']}.",
                  f"- Provincias resueltas por código provincial único: {checks['enemdu']['provincias_recuperadas']}.",
                  f"- Provincias que siguen pendientes: {checks['enemdu']['provincia_pendiente']}.",
                  '- Los cantones ambiguos siguen pendientes; no se asignan nombres por mayoría.',
                  '- No se aplicaron media, mediana, moda ni ceros para completar observaciones.', '',
                  '## Selección', '',
                  'Cada fuente tiene seleccion_variables.csv con todas las columnas clean, su cobertura y decisión.',
                  'diccionario_vista.csv describe cada alias, rol, cobertura y tratamiento de faltantes.',
                  'Se excluyen numeraciones, copias originales, identificación no necesaria y variables fuera del alcance.',
                  'Estrato, UPM y factor de expansión se conservan como diseño muestral, no como predictores por defecto.', '',
                  '## Universos y límites', '',
                  '- Una fila continúa siendo un registro de fuente; no se deduplica ni se filtra una cohorte de forma silenciosa.',
                  '- Las frecuencias deben indicar número válido y faltante; un NULL no se convierte en cero.',
                  '- Las variables de aplicación específica requieren denominador apropiado.',
                  '- Se conserva edad abierta sin convertirla en edad exacta; el grupo 65+ se conoce por su límite inferior.',
                  '- El diseño de encuesta y los cambios de categorías requieren revisión antes de estimaciones poblacionales.',
                  '- Una nueva consulta ve los datos de clean; el gráfico o cliente tiene que volver a consultar.',
                  '- La próxima sustitución física de clean debe coordinar el recreado de vistas; el publicador actual se detiene ante dependencias.', '',
                  '## Conservación', '', f"Estado de controles: **{conservation['status']}**.",
                  'Se compararon identidades, estructura, conteos y contadores DML; estos controles no son hashes de contenido.',
                  'El SQL persistente creado por este proceso solo define vistas en analitica.', ''])
    (directory / 'resultado.md').write_text('\n'.join(lines), encoding='utf-8')


def imputation_decisions(results):
    decisions = []
    for view in VIEWS:
        for item in results[view.name]['profile']:
            name, role = item['variable'], item['rol']
            if name == 'dias_hasta_localizacion':
                decision = 'DERIVACION_DE_FECHAS_OBSERVADAS'
            elif view.name == 'v_enemdu' and name == 'provincia':
                decision = 'RESOLUCION_CATALOGO_PROVINCIAL_UNICO'
            elif role in ('procedencia', 'control', 'diseno_muestral'):
                decision = 'NO_IMPUTAR_CAMPO_TECNICO'
            elif item['null_sql'] == 0:
                decision = 'SIN_NULOS_SQL_NO_NECESARIA'
            elif role == 'condicional':
                decision = 'NO_IMPUTAR_GLOBALMENTE_REVISAR_UNIVERSO'
            else:
                decision = 'CONSERVAR_FALTANTES_ANALISIS_DESCRIPTIVO'
            decisions.append({'vista': view.name, 'variable': name, 'rol': role,
                              'null_sql': item['null_sql'], 'pct_null_sql': item['pct_null_sql'],
                              'decision': decision, 'imputacion_estadistica': False,
                              'justificacion': item['tratamiento_faltantes']})
    return decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('vistas_%Y%m%d_%H%M%S'))
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9_]{1,30}', args.run_id):
        parser.error('Identificador inválido')
    if args.plan:
        for name, query in definitions().items():
            print(f'-- Vista normal: {SCHEMA}.{name}\n{query};\n')
        return
    directory = PROJECT_ROOT / 'reports' / 'analitica' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'run_id': args.run_id, 'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(),
                'schema': SCHEMA, 'statistical_imputation': False,
                'source_hashes': {path: hashlib.sha256((PROJECT_ROOT / path).read_bytes()).hexdigest()
                                  for path in ('utils/analytic_views.py', 'scripts/create_analytic_views.py')}}
    write_json(directory / 'manifest.json', manifest)
    write_json(directory / 'contrato_vistas.json', {
        view.name: {'source': 'clean.' + view.table, 'grain': view.grain,
                    'purpose': view.purpose, 'sql': view.sql,
                    'fields': [vars(field) for field in view.fields]} for view in VIEWS})
    try:
        before = snapshot_existing()
        write_json(directory / 'protected_before.json', before)
        create_views()
        results = {}
        with engine.connect() as conn, conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='20min'"))
            conn.execute(text('SET LOCAL jit=off'))
            for view in VIEWS:
                source_dir = directory / view.name
                source_dir.mkdir()
                expected = before['clean.' + view.table]['rows']
                log(f'Perfil y selección: {SCHEMA}.{view.name}')
                source_selection(conn, view, source_dir, expected)
                results[view.name] = view_profile(conn, view, source_dir, expected)
                log(f'{view.name}: {expected:,} filas conservadas, {len(view.fields)} campos')
            checks = deterministic_checks(conn)
        write_json(directory / 'recuperaciones_y_controles.json', checks)
        write_csv(directory / 'decisiones_imputacion.csv', imputation_decisions(results))
        after = snapshot_existing()
        write_json(directory / 'protected_after.json', after)
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        conservation = {'status': 'UNCHANGED' if not changed else 'CHANGED_REQUIRES_REVIEW', 'changed_objects': changed,
                        'scope': 'estructura, identidades, conteos, definiciones de vistas y contadores DML; sin hash de contenido'}
        write_json(directory / 'conservacion.json', conservation)
        write_report(directory, results, checks, conservation)
        if changed:
            raise AssertionError(f'Cambios externos en las capas existentes: {changed}')
        manifest.update(status='COMPLETED', views={name: 'VIEW' for name in definitions()},
                        results={name: {'rows': item['rows'], 'columns': item['columns']} for name, item in results.items()})
        log(f'Finalizado. Reporte: {directory / "resultado.md"}')
    except BaseException as error:
        manifest.update(status='FAILED', error=str(error))
        (directory / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(directory / 'manifest.json', manifest)


if __name__ == '__main__':
    main()
