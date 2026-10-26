"""API del dashboard: contratos agregados, filtros compartidos y cargas coherentes."""
from contextlib import contextmanager
import csv
from decimal import Decimal
import json
import math
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from utils.config import engine, PROJECT_ROOT
from utils.analytic_views import PROVINCES


router = APIRouter(prefix='/api/v1', tags=['Dashboard'])
SOURCES = {'homicidios', 'armas', 'desapariciones', 'defunciones'}
JOIN = '''FROM dwh.web_fact_seguridad f JOIN dwh.web_dim_tiempo t USING(tiempo_key)
          JOIN dwh.web_dim_territorio g USING(territorio_key)'''


def safe(value):
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, Decimal):
        return safe(float(value))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


@contextmanager
def reader():
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            state = conn.execute(text('''SELECT c.batch_id,c.created_at,c.metadata FROM dwh.web_estado e
                JOIN dwh.web_cargas c ON c.batch_id=e.active_batch_id WHERE e.singleton=1''')).mappings().first()
            if not state:
                raise HTTPException(503, 'El DW de consulta aún no tiene una carga. Ejecutar python -m scripts.update_dashboard.')
            yield conn, dict(state)
    except DBAPIError as error:
        if getattr(error.orig, 'pgcode', None) == '42P01':
            raise HTTPException(503, 'Inicializar el DW con python -m scripts.update_dashboard.') from error
        raise


def rows(conn, sql, params):
    return [dict(row) for row in conn.execute(text(sql), params).mappings()]


def validate_filters(start, end, provinces):
    if start > end or end-start > 30:
        raise HTTPException(422, 'Selecciona un período ordenado de hasta 31 años.')
    provinces = list(dict.fromkeys(provinces or []))
    if len(provinces) > 4 or any(province not in PROVINCES for province in provinces):
        raise HTTPException(422, 'Selecciona hasta cuatro provincias reconocidas.')
    return provinces


def where(params, geographic=True):
    clause = 'f.batch_id=:batch AND f.fuente=:source AND t.anio BETWEEN :start AND :end'
    if geographic and params['provinces']:
        clause += ' AND g.provincia=ANY(:provinces)'
    return clause


def change(current, previous):
    return (current-previous)/previous*100 if previous is not None and previous>0 and current is not None else None


@router.get('/meta')
def meta():
    with reader() as (conn, state):
        coverage = state['metadata']['coverage']['homicidios']
        years = [item['anio'] for item in coverage]
        full = [item['anio'] for item in coverage if len(item['meses']) == 12]
        end = max(full or years)
        return safe({**state, 'provinces': sorted(PROVINCES), 'years': years,
                     'defaults': {'start': max(min(years), 2018), 'end': end},
                     'unit': 'Registros de la fuente; no equivalen automáticamente a eventos únicos.',
                     'context_status': 'Exploratorio: diciembre no equivale a ENEMDU anual provincial.'})


@router.get('/dashboard')
def dashboard(source: str = 'homicidios', start: int = Query(2018, ge=1800, le=2100),
              end: int = Query(2024, ge=1800, le=2100), provinces: list[str] | None = Query(None),
              frequency: str = 'annual', heatmap: str = 'annual'):
    provinces = validate_filters(start, end, provinces)
    if source not in SOURCES or frequency not in ('annual','monthly') or heatmap not in ('annual','monthly'):
        raise HTTPException(422, 'Fuente o granularidad no válida.')
    with reader() as (conn, state):
        params = {'batch': state['batch_id'], 'source': source, 'start': start, 'end': end, 'provinces': provinces}
        condition = where(params)
        totals = rows(conn, f'''SELECT sum(f.registros)::bigint registros,
            sum(f.cantidad) cantidad,sum(f.cantidad_informada)::bigint cantidad_informada,
            sum(f.duracion_sum)/nullif(sum(f.duracion_n),0) promedio_dias_observados,
            sum(f.duracion_n)::bigint duraciones_observadas {JOIN} WHERE {condition}''', params)[0]
        national = conn.execute(text(f'SELECT sum(f.registros) {JOIN} WHERE {where(params,False)}'),params).scalar_one()
        annual = rows(conn, f'SELECT t.anio,sum(f.registros)::bigint registros {JOIN} WHERE {condition} GROUP BY 1 ORDER BY 1', params)
        month_expression = 't.mes' if frequency == 'monthly' else 'NULL::integer'
        trend = rows(conn, f'''SELECT t.anio,{month_expression} mes,g.provincia,sum(f.registros)::bigint registros
            {JOIN} WHERE {condition} GROUP BY 1,2,3 ORDER BY 1,2,3''', params)
        national_trend = rows(conn, f'''SELECT t.anio,{month_expression} mes,sum(f.registros)::bigint registros
            {JOIN} WHERE {where(params,False)} GROUP BY 1,2 ORDER BY 1,2''', params)
        sexes = rows(conn, f'SELECT f.sexo,sum(f.registros)::bigint registros {JOIN} WHERE {condition} GROUP BY 1 ORDER BY 2 DESC', params)
        ages = rows(conn, f'SELECT f.grupo_edad,sum(f.registros)::bigint registros {JOIN} WHERE {condition} GROUP BY 1 ORDER BY 1', params)
        categories = rows(conn, f'SELECT f.categoria,sum(f.registros)::bigint registros {JOIN} WHERE {condition} GROUP BY 1 ORDER BY 2 DESC', params)
        territories = rows(conn, f'''SELECT g.provincia,g.canton,sum(f.registros)::bigint registros
            {JOIN} WHERE {condition} GROUP BY 1,2 ORDER BY 3 DESC,1,2''', params)
        heat_month = 't.mes' if heatmap == 'monthly' else 'NULL::integer'
        heat = rows(conn, f'''SELECT t.anio,{heat_month} mes,g.provincia,sum(f.registros)::bigint registros
            {JOIN} WHERE {condition} GROUP BY 1,2,3 ORDER BY 1,2,3''', params)
        coverage = [item for item in state['metadata']['coverage'][source] if start<=item['anio']<=end]
        month_lookup = {item['anio']: item['meses'] for item in state['metadata']['coverage'][source]}
        shared = sorted(set(month_lookup.get(end, [])) & set(month_lookup.get(end-1, [])))
        comparison = {'year': end, 'previous_year': end-1, 'months': shared, 'current': None, 'previous': None, 'percent': None}
        if shared:
            p = {**params, 'start': end-1, 'end': end, 'months': shared}
            comparable = rows(conn, f'''SELECT t.anio,sum(f.registros)::bigint registros {JOIN}
                WHERE {where(p)} AND t.mes=ANY(:months) GROUP BY 1''', p)
            lookup = {item['anio']: item['registros'] for item in comparable}
            comparison.update(current=lookup.get(end), previous=lookup.get(end-1))
            comparison['percent'] = change(comparison['current'], comparison['previous'])
        total = totals['registros']
        leading = rows(conn, f'SELECT g.provincia,sum(f.registros)::bigint registros {JOIN} WHERE {condition} GROUP BY 1 ORDER BY 2 DESC LIMIT 1', params)
        return safe({'batch_id': state['batch_id'], 'loaded_at': state['created_at'],
                     'filters': {'source': source,'start': start,'end': end,'provinces': provinces,'frequency': frequency,'heatmap': heatmap},
                     'totals': {**totals,'source_total': national,'selected_share_pct': total/national*100 if total is not None and national else None},
                     'annual': annual,'trend': trend,'national_trend': national_trend,'sexes': sexes,'ages': ages,
                     'categories': categories,'territories': territories,'heatmap': heat,'coverage': coverage,
                     'comparison': comparison,'leading': leading[0] if leading else None,
                     'has_data': total is not None,
                     'notes': ['Los espacios sin registros observados no se convierten en cero.',
                               'Los totales conservan candidatos a duplicación; no son tasas por habitante.']})


@router.get('/context')
def context(start: int = Query(2018, ge=1800, le=2100), end: int = Query(2024, ge=1800, le=2100),
            provinces: list[str] | None = Query(None)):
    provinces = validate_filters(start,end,provinces)
    with reader() as (conn,state):
        p = {'batch':state['batch_id'],'start':start,'end':end,'provinces':provinces,'source':'homicidios'}
        geo = ' AND g.provincia=ANY(:provinces)' if provinces else ''
        data = rows(conn, f'''SELECT t.anio,g.provincia,sum(f.registros)::bigint muestra,
            sum(f.pobreza_validos)::bigint pobreza_validos,sum(f.ingreso_validos)::bigint ingreso_validos,
            sum(f.pobreza_num) pobreza_num,sum(f.pobreza_den) pobreza_den,
            sum(f.ingreso_num) ingreso_num,sum(f.ingreso_den) ingreso_den
            FROM dwh.web_fact_contexto f JOIN dwh.web_dim_tiempo t USING(tiempo_key)
            JOIN dwh.web_dim_territorio g USING(territorio_key)
            WHERE f.batch_id=:batch AND t.anio BETWEEN :start AND :end AND t.mes=12 {geo}
            GROUP BY 1,2 ORDER BY 1,2''',p)
        security = rows(conn, f'SELECT t.anio,g.provincia,sum(f.registros)::bigint registros {JOIN} WHERE {where(p)} GROUP BY 1,2',p)
        lookup = {(item['anio'],item['provincia']): item['registros'] for item in security}
        for item in data:
            item['pobreza_pct'] = item['pobreza_num']/item['pobreza_den']*100 if item['pobreza_den'] else None
            item['ingreso_per_capita'] = item['ingreso_num']/item['ingreso_den'] if item['ingreso_den'] else None
            item['homicidios'] = lookup.get((item['anio'],item['provincia']))
        series = []
        for year in sorted({item['anio'] for item in data}):
            subset = [item for item in data if item['anio']==year]
            pn = sum((item['pobreza_num'] or 0) for item in subset)
            pd = sum((item['pobreza_den'] or 0) for item in subset)
            inn = sum((item['ingreso_num'] or 0) for item in subset)
            ind = sum((item['ingreso_den'] or 0) for item in subset)
            series.append({'anio':year,'pobreza_pct':pn/pd*100 if pd else None,'ingreso_per_capita':inn/ind if ind else None})
        return safe({'batch_id':state['batch_id'],'data':data,'series':series,
                     'paired':sum(item['homicidios'] is not None and item['pobreza_pct'] is not None for item in data),
                     'sample_records':sum(item['muestra'] for item in data), 'official':False,
                     'note':'Diciembre: razones ponderadas exploratorias. Requiere validar dominio, diseño y versiones ENEMDU; no es una tasa provincial anual oficial.'})


def research_run():
    root = PROJECT_ROOT/'reports'/'investigacion'
    configured = os.environ.get('RESEARCH_RUN_ID')
    candidates = [root/configured] if configured and Path(configured).name==configured else sorted(root.glob('*'),reverse=True)
    for directory in candidates:
        manifest_path = directory/'manifest.json'
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('status')=='COMPLETED' and (directory/'metricas.csv').is_file():
                return directory,manifest
    return None,None


def csv_records(path):
    with path.open(encoding='utf-8-sig',newline='') as file:
        result = list(csv.DictReader(file))
    for row in result:
        for key,value in row.items():
            if value=='':
                row[key]=None
            else:
                try:
                    row[key]=float(value) if any(ch in value.lower() for ch in ('.','e')) else int(value)
                except ValueError:
                    pass
    return result


@router.get('/evaluation')
def evaluation(province: str | None = None):
    if province and province not in PROVINCES:
        raise HTTPException(422,'Provincia no reconocida')
    directory,manifest = research_run()
    if directory is None:
        return {'available':False,'note':'Aún no existe una evaluación temporal completada. Ejecutar python -m analysis.run_provincial_study.'}
    metrics = csv_records(directory/'metricas.csv')
    predictions = [row for row in csv_records(directory/'predicciones_fuera_de_tiempo.csv')
                   if row['scenario']=='registros_contexto_lag2' and (not province or row['provincia']==province)]
    forecast = [row for row in csv_records(directory/'proyeccion_retrospectiva_2025.csv')
                if row['model'] in ('ultimo_anio','promedio_dos_anios') and (not province or row['provincia']==province)]
    with reader() as (_,state):
        versions = manifest.get('clean_versions',{})
        outdated = (versions.get('homicidio_limpia') != [state['metadata']['source_versions']['homicidios']]
                    or versions.get('enemdu_limpia') != [state['metadata']['source_versions']['enemdu']])
    return safe({'available':True,'run_id':manifest['run_id'],'created_at':manifest.get('finished_at'),
                 'outdated':outdated,'ready_for_production':False,
                 'metrics':[row for row in metrics if row['scenario']=='registros_contexto_lag2'],
                 'predictions':predictions,'forecast':forecast,'results':manifest['results'],
                 'note':'Evaluación retrospectiva: referencias sencillas frente a modelos. Proyecciones 2025 experimentales; no evaluadas contra un año completo.'})


@router.get('/map')
def map_status():
    path = PROJECT_ROOT/'web'/'public'/'maps'/'ecuador_provincias.geojson'
    if not path.is_file():
        return {'available':False,'note':'Mapa geográfico opcional: cartografía provincial verificada aún no incorporada. La matriz temporal sí está disponible.'}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('type')!='FeatureCollection':
        raise HTTPException(503,'Cartografía no válida')
    features = data.get('features', [])
    codes = []
    for feature in features:
        properties = feature.get('properties', {})
        code = str(properties.get('codigo_provincia', '')).zfill(2)
        if code not in {str(i).zfill(2) for i in range(1,25)} or feature.get('geometry', {}).get('type') not in ('Polygon','MultiPolygon'):
            return {'available':False,'note':'La cartografía necesita códigos DPA provinciales y geometrías Polygon/MultiPolygon verificadas.'}
        codes.append(code)
        properties['name'] = PROVINCES[int(code)-1]
        feature['properties'] = properties
    if len(codes)!=24 or len(set(codes))!=24:
        return {'available':False,'note':'El archivo debe contener las 24 provincias sin códigos duplicados.'}
    return {'available':True,'geojson':data}
