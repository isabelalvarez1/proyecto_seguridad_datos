"""Actualizar el mart web de forma atómica; conserva dos cargas completas."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import uuid

from sqlalchemy import text

from utils.config import engine, PROJECT_ROOT
from utils.dashboard_dw import DDL, SECURITY_SOURCES, security_sql, CONTEXT_SQL, assert_totals


def refresh(retain=2):
    if retain < 2:
        raise ValueError('Conservar al menos dos cargas para actualización y recuperación')
    batch = datetime.now(timezone.utc).strftime('web_%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6]
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('dashboard_refresh'))"))
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('proyecto_ecuador_clean_publication'))"))
        conn.execute(text("SET LOCAL statement_timeout='20min'"))
        conn.execute(text('SET LOCAL jit=off'))
        conn.execute(text(DDL))
        print('Agregando seguridad desde vistas analíticas...', flush=True)
        conn.execute(text('CREATE TEMP TABLE web_stage_security ON COMMIT DROP AS ' + security_sql()))
        print('Agregando contexto con denominadores válidos...', flush=True)
        conn.execute(text('CREATE TEMP TABLE web_stage_context ON COMMIT DROP AS ' + CONTEXT_SQL))
        metadata = {'contract': 1, 'unit': 'registros de fuente, sin deduplicación automática',
                    'analytic_contract_sha256': hashlib.sha256((PROJECT_ROOT/'utils/analytic_views.py').read_bytes()).hexdigest(),
                    'source_versions': {}, 'source_counts': {}, 'coverage': {}}
        for source, (view, *_) in SECURITY_SOURCES.items():
            count = conn.execute(text(f'SELECT count(*) FROM analitica.{view}')).scalar_one()
            actual = conn.execute(text('SELECT sum(registros) FROM web_stage_security WHERE fuente=:s'), {'s': source}).scalar_one()
            assert_totals(count, int(actual or 0))
            versions = conn.execute(text(f'SELECT DISTINCT version_clean FROM analitica.{view}')).scalars().all()
            if len(versions) != 1:
                raise ValueError(f'Versiones mezcladas en {view}')
            metadata['source_versions'][source] = versions[0]
            metadata['source_counts'][source] = count
            coverage = conn.execute(text("""SELECT tiempo_key/100 anio,array_agg(DISTINCT tiempo_key%100 ORDER BY tiempo_key%100) meses,
                sum(registros)::bigint registros FROM web_stage_security WHERE fuente=:s AND tiempo_key>0 GROUP BY 1 ORDER BY 1"""), {'s': source}).mappings().all()
            metadata['coverage'][source] = [dict(row) for row in coverage]
        context_count = conn.execute(text('SELECT count(*) FROM analitica.v_enemdu')).scalar_one()
        assert_totals(context_count, int(conn.execute(text('SELECT sum(registros) FROM web_stage_context')).scalar_one() or 0))
        versions = conn.execute(text('SELECT DISTINCT version_clean FROM analitica.v_enemdu')).scalars().all()
        if len(versions) != 1:
            raise ValueError('Versiones mezcladas en ENEMDU')
        metadata['source_versions']['enemdu'] = versions[0]
        metadata['source_counts']['enemdu'] = context_count
        metadata['context_without_period'] = int(conn.execute(text('SELECT COALESCE(sum(registros),0) FROM web_stage_context WHERE tiempo_key=0')).scalar_one())
        metadata['coverage']['enemdu'] = [dict(row) for row in conn.execute(text("""
            SELECT tiempo_key/100 anio,array_agg(DISTINCT tiempo_key%100 ORDER BY tiempo_key%100) meses,
                sum(registros)::bigint registros,sum(pobreza_validos)::bigint pobreza_validos
            FROM web_stage_context WHERE tiempo_key>0 GROUP BY 1 ORDER BY 1
        """)).mappings()]
        conn.execute(text("""INSERT INTO dwh.web_dim_tiempo
            SELECT k,CASE WHEN k>0 THEN k/100 END,CASE WHEN k>0 THEN k%100 END
            FROM (SELECT tiempo_key k FROM web_stage_security UNION SELECT tiempo_key FROM web_stage_context) q
            ON CONFLICT DO NOTHING"""))
        conn.execute(text("""INSERT INTO dwh.web_dim_territorio(provincia,canton,provincia_ref,canton_ref)
            SELECT provincia,canton,COALESCE(provincia,'__NULL_PROVINCIA__'),COALESCE(canton,'__NULL_CANTON__')
            FROM (SELECT provincia,canton FROM web_stage_security UNION SELECT provincia,canton FROM web_stage_context) q
            ON CONFLICT(provincia_ref,canton_ref) DO NOTHING"""))
        conn.execute(text('INSERT INTO dwh.web_cargas(batch_id,metadata) VALUES(:b,CAST(:m AS jsonb))'),
                     {'b': batch, 'm': json.dumps(metadata, ensure_ascii=False)})
        conn.execute(text("""INSERT INTO dwh.web_fact_seguridad
            SELECT :b,s.fuente,s.tiempo_key,g.territorio_key,s.sexo,s.grupo_edad,s.categoria,
                s.registros,s.cantidad,s.cantidad_informada,s.duracion_sum,s.duracion_n
            FROM web_stage_security s JOIN dwh.web_dim_territorio g
              ON g.provincia_ref=COALESCE(s.provincia,'__NULL_PROVINCIA__') AND g.canton_ref=COALESCE(s.canton,'__NULL_CANTON__')"""), {'b': batch})
        conn.execute(text("""INSERT INTO dwh.web_fact_contexto
            SELECT :b,s.tiempo_key,g.territorio_key,s.registros,s.pobreza_validos,s.ingreso_validos,
                s.pobreza_num,s.pobreza_den,s.ingreso_num,s.ingreso_den,s.pesos2
            FROM web_stage_context s JOIN dwh.web_dim_territorio g
              ON g.provincia_ref=COALESCE(s.provincia,'__NULL_PROVINCIA__') AND g.canton_ref='__NULL_CANTON__'"""), {'b': batch})
        for source, expected in metadata['source_counts'].items():
            if source == 'enemdu':
                value = conn.execute(text('SELECT sum(registros) FROM dwh.web_fact_contexto WHERE batch_id=:b'), {'b': batch}).scalar_one()
            else:
                value = conn.execute(text('SELECT sum(registros) FROM dwh.web_fact_seguridad WHERE batch_id=:b AND fuente=:s'), {'b': batch, 's': source}).scalar_one()
            assert_totals(expected, int(value or 0))
        conn.execute(text("""INSERT INTO dwh.web_estado VALUES(1,:b)
            ON CONFLICT(singleton) DO UPDATE SET active_batch_id=excluded.active_batch_id"""), {'b': batch})
        conn.execute(text("""DELETE FROM dwh.web_cargas WHERE batch_id NOT IN
            (SELECT batch_id FROM dwh.web_cargas ORDER BY created_at DESC,batch_id DESC LIMIT :n)"""), {'n': retain})
    print(f'Carga publicada: {batch}; totales: {metadata["source_counts"]}', flush=True)
    return batch, metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retain', type=int, default=2)
    refresh(parser.parse_args().retain)
