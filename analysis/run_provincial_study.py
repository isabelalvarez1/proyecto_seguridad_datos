"""Estudio agregado y validación temporal, con PostgreSQL estrictamente READ ONLY.

No publica modelos en la API ni modifica raw/clean/DW/vistas/dashboard.
python -m analysis.run_provincial_study
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import traceback
import warnings

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text

from analysis.run_clean_validation import write_json, log
from analysis.provincial_panel import (
    extract_aggregates, build_history, descriptive_panel, forecasting_panel, next_year_features,
    HOMICIDES_SQL, SURVEY_SQL, COVERAGE_SQL, validate_survey_aggregates,
)
from ml.provincial_evaluation import evaluate, summarize, paired_comparison, MODEL_NAMES, predict_one
from utils.config import engine, PROJECT_ROOT


OFFICIAL_REFERENCES = [
    {'url': 'https://www.ecuadorencifras.gob.ec/enemdu-anual/',
     'finding': 'La ENEMDU anual permite mayor desagregación provincial; no se produjo anual 2020. No equiparar diciembre con estimación anual.'},
    {'url': 'https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/',
     'finding': 'INEC documenta cambios de muestra, representatividad y ponderación entre 2020 y mayo 2021.'},
    {'url': 'https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2021/Nota_tecnica/202106_Nota_tecnica_ENEMDU.pdf',
     'finding': 'Nota técnica vinculada por INEC; requiere revisión de versión aplicable a los archivos locales.'},
]


def save_csv(path, frame):
    frame.to_csv(path, index=False, encoding='utf-8-sig', float_format='%.10g')


def source_identity(conn):
    return [dict(row) for row in conn.execute(text("""
        SELECT n.nspname schema,c.relname name,c.oid::bigint oid,c.relfilenode::bigint filenode,c.relkind kind,
               CASE WHEN c.relkind IN ('v','m') THEN pg_get_viewdef(c.oid,true) END definition
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('raw','clean','dwh','catalogo','analitica') AND c.relkind IN ('r','p','m','v')
        ORDER BY 1,2
    """)).mappings()]


def complementary_extracts(conn, history):
    arms = pd.read_sql(text("""
        SELECT extract(year from fecha_evento)::integer anio,nombre_provincia provincia,
               count(*) registros_armas,count(DISTINCT _raw_hash) hashes_distintos_armas,
               count(cantidad) cantidades_informadas,sum(cantidad) cantidad_observada
        FROM clean.mdi_arma_limpia
        WHERE fecha_evento BETWEEN '2017-01-01' AND '2024-12-31'
        GROUP BY 1,2
    """), conn)
    joined = history.loc[history.anio.between(2017,2024)].merge(arms, on=['provincia','anio'], how='left', validate='one_to_one')
    joined['interpretacion'] = 'REGISTROS_NO_EVENTOS_UNICOS; NO_INTERPRETAR_ASOCIACION_COMO_EFECTO_POLICIAL'
    mortality = pd.read_sql(text("""
        SELECT extract(year from fecha_fall)::integer anio,prov_fall provincia,
               count(*) registros_defuncion,
               count(*) FILTER(WHERE mor_viol='HOMICIDIOS') etiqueta_homicidio,
               count(*) FILTER(WHERE substring(causa from 1 for 3) BETWEEN 'X85' AND 'X99'
                               OR substring(causa from 1 for 3) BETWEEN 'Y00' AND 'Y09') prefijo_cie_agresion
        FROM clean.edg_limpia WHERE fecha_fall BETWEEN '2017-01-01' AND '2024-12-31'
        GROUP BY 1,2
    """), conn)
    contrast = history.loc[history.anio.between(2017,2024)].merge(mortality, on=['provincia','anio'], how='left', validate='one_to_one')
    contrast['interpretacion'] = 'REQUIERE_HOMOLOGAR_CAUSA_FECHA_Y_TERRITORIO; EDG_2017_TIENE_DESCRIPCIONES_SIN_CODIGO'
    return joined, contrast


def exploratory_correlations(panel):
    data = panel.loc[panel.elegible_cruce_exploratorio].copy()
    rows = []
    groups = [('POOL_2018_2024', data)] + [(str(year), subset) for year, subset in data.groupby('anio')]
    for label, subset in groups:
        for variable in ('pobreza_ponderada', 'ingreso_ponderado'):
            valid = subset[['registros', variable]].dropna()
            pearson = valid.registros.corr(valid[variable]) if len(valid)>2 else np.nan
            spearman = valid.registros.rank().corr(valid[variable].rank()) if len(valid)>2 else np.nan
            rows.append({'periodo': label, 'variable': variable, 'n_pares': len(valid),
                         'pearson_no_ajustado': pearson, 'spearman_no_ajustado': spearman,
                         'inferencia': 'EXPLORATORIO_SIN_AJUSTE_POBLACIONAL_NI_DISENO_MUESTRAL; NO_CAUSAL'})
    return pd.DataFrame(rows)


def protocol(last_year, context_lag):
    return {
        'question': '¿Mejora el contexto socioeconómico previo la predicción territorial de registros de homicidio frente al historial?',
        'unit': 'provincia-año; registro de fuente, no persona/evento único confirmado',
        'descriptive_years': [2018, last_year], 'survey_round': 'Diciembre; NO equivale a ENEMDU anual provincial',
        'context_lag_years': context_lag, 'release_dates_verified': False,
        'operational_backtest': False,
        'forecast_interpretation': 'Pseudopronóstico retrospectivo con orden temporal; no reconstruye versiones ni fechas reales de publicación.',
        'population_available': False, 'outcome': 'conteos de registros; no tasas de riesgo por habitante',
        'official_provincial_survey_domain_verified': False,
        'survey_estimators': 'Razones ponderadas experimentales sobre respuestas válidas de diciembre.',
        'survey_uncertainty': 'Kish es diagnóstico de dispersión de pesos, no error estándar del diseño ni certificación de representatividad.',
        'income': 'Ingreso nominal; no se dispone de deflactor en este experimento.',
        'target_missingness': 'Ausencia de filas provincia-año no se convierte automáticamente en cero.',
        'comparability': 'Misma cohorte y mismo conjunto de entrenamiento para historial y contexto; sin imputador.',
        'numeric_features_history': ['log_lag_1', 'log_lag_2', 'tendencia_anio'],
        'extra_context_features': ['pobreza_ponderada', 'log_ingreso'],
        'categorical_features': ['provincia'],
        'models': {'PoissonRegressor': {'alpha': 1.0, 'max_iter': 5000},
                   'RandomForestRegressor': {'n_estimators': 200, 'max_depth': 4, 'min_samples_leaf': 5, 'random_state': 42}},
        'references': ['ultimo_anio', 'promedio_dos_anios'],
        'evaluation': 'Ventana expansiva; entrenar años anteriores, evaluar 2022 y 2023; 2024 holdout final. Hiperparámetros fijados antes de observar métricas.',
        'sensitivity': ['colapsar hashes como sensibilidad, no como deduplicación aprobada',
                        'excluir ronda ENEMDU diciembre 2020; no elimina toda influencia de pandemia en historial'],
        'not_implemented': ['promoción a API', 'predicción 2026 con 2025 anual incompleto',
                            'tasas poblacionales', 'intervalos oficiales ENEMDU', 'inferencia causal'],
        'references_official': OFFICIAL_REFERENCES,
    }


def make_figures(directory, crime, panel, metric_table, predictions):
    primary = crime.loc[crime.anio.between(2014,2024)].groupby('anio')[['registros','hashes_distintos']].sum()
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(primary.index, primary.registros, marker='o', label='Registros conservados')
    ax.plot(primary.index, primary.hashes_distintos, linestyle='--', label='Hashes distintos (sensibilidad)')
    ax.set(xlabel='Año', ylabel='Registros', title='Evolución observada; no equivale a personas únicas verificadas')
    ax.legend(); fig.tight_layout(); fig.savefig(directory/'tendencia_registros.png',dpi=200); plt.close(fig)
    data = panel.loc[panel.elegible_cruce_exploratorio]
    fig, ax = plt.subplots(figsize=(9,5))
    points = ax.scatter(data.pobreza_ponderada*100,data.registros,c=data.anio,cmap='viridis',alpha=0.65)
    ax.set(xlabel='Proporción ponderada experimental de diciembre (%)', ylabel='Registros de homicidio',
           title='Cruce sin ajuste poblacional; no es estimación oficial ni causal')
    fig.colorbar(points,ax=ax,label='Año'); fig.tight_layout(); fig.savefig(directory/'dispersion_exploratoria.png',dpi=200); plt.close(fig)
    table = metric_table.loc[metric_table.scenario.eq('registros_contexto_lag2') & metric_table.phase.eq('HOLDOUT_FINAL_2024')].sort_values('mae')
    if not table.empty:
        fig, ax = plt.subplots(figsize=(9,4))
        ax.barh(table.model,table.mae,color='#2372a8'); ax.invert_yaxis()
        ax.set(xlabel='MAE (registros por provincia)', title='Holdout temporal 2024; modelos y referencias predefinidos')
        fig.tight_layout(); fig.savefig(directory/'mae_holdout_2024.png',dpi=200); plt.close(fig)
    data = predictions.loc[predictions.scenario.eq('registros_contexto_lag2') & predictions.model.isin(['ultimo_anio','poisson_historial','poisson_contexto'])]
    if not data.empty:
        fig, ax = plt.subplots(figsize=(8,5))
        for name, group in data.groupby('model'):
            ax.scatter(group.actual,group.predicted,label=name,alpha=0.5)
        maximum = max(data.actual.max(),data.predicted.max())
        ax.plot([0,maximum],[0,maximum],'k--',linewidth=1)
        ax.set(xlabel='Observado',ylabel='Predicho',title='Predicciones fuera de tiempo, 2022–2024')
        ax.legend(); fig.tight_layout(); fig.savefig(directory/'observado_predicho.png',dpi=200); plt.close(fig)


def write_report(directory, results, panel, forecast_frame, metric_table, comparison, folds):
    selected = metric_table.loc[metric_table.scenario.eq('registros_contexto_lag2') & metric_table.phase.eq('HOLDOUT_FINAL_2024')]
    lines = ['# Estudio provincia-año y evaluación predictiva', '',
             '## Estado de uso', '',
             '**EXPERIMENTO RETROSPECTIVO EXPLORATORIO. NO LISTO PARA INFERENCIA PROVINCIAL OFICIAL NI API.**', '',
             'La documentación INEC distingue ENEMDU anual (mayor desagregación provincial) de rondas mensuales.',
             'La selección local de diciembre no se convierte en una estimación anual por agregar ponderadores.',
             'Se conserva como experimento y se necesita verificar/reemplazar los indicadores provinciales antes de la publicación científica.', '',
             '## Datos', '',
             f"- Pares de la cuadrícula descriptiva: {len(panel)}; pares observados con contexto: {int(panel.elegible_cruce_exploratorio.sum())}.",
             f"- Filas de comparación predictiva completas: {results['eligible_prediction_rows']}.",
             '- Las filas sin registros no se convierten en cero y los faltantes de contexto no se imputan.',
             '- Contexto con dos años de rezago; fechas históricas de publicación y revisiones no reconstruidas.',
             '- No hay población oficial cargada: no se calculan tasas por 100.000 habitantes.', '',
             '## Holdout final 2024, escenario principal', '',
             '| Modelo | n | MAE | RMSE | WAPE % |', '|---|---:|---:|---:|---:|']
    for _, row in selected.sort_values('mae').iterrows():
        lines.append(f'| {row.model} | {int(row.n)} | {row.mae:.3f} | {row.rmse:.3f} | {row.wape_pct:.2f} |')
    lines.extend(['', 'No se eligieron hiperparámetros usando 2024; Poisson es la familia principal predefinida y RF una comprobación secundaria.',
                  'Los modelos usan conteos sin offset poblacional: no explican riesgo individual ni efectos de pobreza.', '',
                  '## ¿Aporta el contexto?', ''])
    pooled = metric_table.loc[metric_table.scenario.eq('registros_contexto_lag2') & metric_table.phase.eq('ALL_TEMPORAL')]
    lines.extend(['| Modelo | MAE conjunto 2022–2024 |', '|---|---:|'])
    for _, row in pooled.sort_values('mae').iterrows():
        lines.append(f'| {row.model} | {row.mae:.3f} |')
    reference_mae = pooled.loc[pooled.model.isin(['ultimo_anio','promedio_dos_anios']),'mae'].min()
    learned_mae = pooled.loc[~pooled.model.isin(['ultimo_anio','promedio_dos_anios']),'mae'].min()
    if reference_mae <= learned_mae:
        lines.extend(['', 'En este experimento la mejor referencia sencilla supera a los modelos ensayados.'])
    else:
        lines.extend(['', 'Algún modelo supera a las referencias en el agregado; revisar holdout, provincias y sensibilidad antes de promoverlo.'])
    main_pair = comparison.loc[comparison.scenario.eq('registros_contexto_lag2')]
    covers_zero = main_pair.bootstrap_cluster_p025.le(0) & main_pair.bootstrap_cluster_p975.ge(0)
    if covers_zero.all():
        lines.append('Las comparaciones principales de contexto tienen intervalos exploratorios que incluyen cero; no se demuestra mejora robusta.')
    else:
        lines.append('Los intervalos del aporte de contexto varían entre modelos/fases; no equivalen a evidencia causal ni corrigen el diseño de encuesta.')
    lines.append('')
    for _, row in comparison.loc[comparison.scenario.eq('registros_contexto_lag2') & comparison.phase.eq('HOLDOUT_FINAL_2024')].iterrows():
        direction = 'reduce' if row.improvement_mae_positive_is_better>0 else 'aumenta'
        lines.append(f'- {row.algorithm}: el contexto {direction} el MAE en {abs(row.improvement_mae_positive_is_better):.3f} registros; '
                     f'intervalo bootstrap exploratorio de mejora [{row.bootstrap_cluster_p025:.3f}, {row.bootstrap_cluster_p975:.3f}].')
    lines.extend(['', 'El bootstrap agrupa por provincia; no incorpora incertidumbre del diseño ENEMDU, cambios de régimen o publicación histórica.',
                  'Consultar comparación por año y provincia; un buen resultado global puede concentrarse en Guayas.', '',
                  '## Proyección adicional', '',
                  f"Se generaron características de 2025 para {len(forecast_frame)} provincias; {int(forecast_frame.features_completas.sum())} tienen historial/contexto completo.",
                  'Las proyecciones 2025 son retrospectivas y NO se evalúan contra enero–noviembre como si fuera un año completo.',
                  'No se genera 2026: falta 2025 completo como lag del año anterior.', '',
                  '## Sensibilidad', '',
                  '- Se evaluó colapso de hashes solo como sensibilidad; no se eliminaron casos en PostgreSQL.',
                  '- Se evaluó exclusión de la ronda ENEMDU diciembre 2020; comparar cantidad de folds y filas antes de interpretar.',
                  '- Los escenarios pueden tener distinto universo temporal; no comparar promedios entre escenarios sin mirar folds.csv.', '',
                  '## Siguientes pasos para el artículo', '',
                  '1. Documentar dominios y versiones ENEMDU; obtener indicadores provinciales anuales oficiales/validados y sus errores de diseño.',
                  '2. Incorporar población oficial provincial por año y un deflactor si se compara ingreso nominal entre años.',
                  '3. Confirmar unidad de observación y resolver candidatos de duplicación con diccionarios/identificadores.',
                  '4. Auditar fechas de publicación y versiones históricas para un pronóstico operativo real.',
                  '5. Repetir el protocolo con esos insumos antes de promover un modelo o hacer afirmaciones sustantivas.',
                  '6. Definir endpoints y dashboard propio con indicadores aprobados, cobertura e incertidumbre.', '',
                  '## Fuentes consultadas', ''])
    lines.extend(f"- {item['url']}: {item['finding']}" for item in OFFICIAL_REFERENCES)
    lines.extend(['', 'PostgreSQL se consultó en transacción READ ONLY. No se modificaron DW, cubos, API, dashboard ni modelos operativos.', ''])
    (directory/'resultado.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('provincial_%Y%m%d_%H%M%S'))
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[a-z0-9_]{1,40}',args.run_id):
        parser.error('Identificador inválido')
    directory = PROJECT_ROOT/'reports'/'investigacion'/args.run_id
    directory.mkdir(parents=True,exist_ok=False)
    manifest = {'run_id':args.run_id,'status':'RUNNING','started_at':datetime.now(timezone.utc).isoformat(),
                'ready_for_production':False,'official_survey_inference_ready':False,
                'database_transaction':'READ ONLY; REPEATABLE READ',
                'versions':{name:importlib.metadata.version(name) for name in ('pandas','numpy','scikit-learn','SQLAlchemy','matplotlib')},
                'code_hashes':{name:hashlib.sha256((PROJECT_ROOT/name).read_bytes()).hexdigest() for name in
                               ('analysis/provincial_panel.py','ml/provincial_evaluation.py','analysis/run_provincial_study.py')}}
    write_json(directory/'manifest.json',manifest)
    write_json(directory/'protocolo.json',protocol(2024,2))
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn,conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='20min'"))
            conn.execute(text('SET LOCAL jit=off'))
            assert conn.execute(text('SHOW transaction_read_only')).scalar_one()=='on'
            identity_before=source_identity(conn)
            manifest['postgres_snapshot']=conn.execute(text('SELECT pg_current_snapshot()::text')).scalar_one()
            log('Extrayendo agregados provincia-año y contexto de diciembre en solo lectura')
            crime,coverage,survey,provinces=extract_aggregates(conn)
            validate_survey_aggregates(survey)
            versions={table:conn.execute(text(f'SELECT DISTINCT _clean_run_id FROM clean.{table}')).scalars().all()
                      for table in ('homicidio_limpia','enemdu_limpia')}
            if any(len(value)!=1 for value in versions.values()):
                raise AssertionError('Fuentes con versiones de limpieza mezcladas')
            manifest['clean_versions']=versions
            history=build_history(crime,coverage,provinces)
            arms,edg=complementary_extracts(conn,history)
            survey_coverage=pd.read_sql(text('SELECT anio,mes,count(*) registros,count(pobreza_binaria) pobreza_valida '
                                             'FROM analitica.v_enemdu GROUP BY anio,mes ORDER BY anio,mes'),conn)
        with engine.connect() as conn,conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            identity_after=source_identity(conn)
        if identity_before!=identity_after:
            raise AssertionError('Identidades/definiciones cambiaron durante la extracción')
        write_json(directory/'identidades_fuentes.json',identity_before)
        write_json(directory/'sql_extraccion.json',{'homicidios':HOMICIDES_SQL,'encuesta':SURVEY_SQL,'cobertura':COVERAGE_SQL})
        for name,frame in [('homicidios_agregados',crime),('cobertura_homicidios',coverage),('encuesta_diciembre_experimental',survey),
                           ('cobertura_encuesta',survey_coverage),('historial_cuadricula',history),('cruce_armas_exploratorio',arms),('contraste_edg_pendiente',edg)]:
            save_csv(directory/(name+'.csv'),frame)
        panel=descriptive_panel(history,survey)
        save_csv(directory/'panel_descriptivo_y_exclusiones.csv',panel)
        save_csv(directory/'correlaciones_exploratorias_no_ajustadas.csv',exploratory_correlations(panel))
        forecasts,folds=[],[]
        primary=None
        scenarios=[('registros_contexto_lag2','registros',False),('hashes_sensibilidad','hashes_distintos',False),
                   ('sin_ronda_enemdu_2020','registros',True)]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            for name,outcome,exclude_2020 in scenarios:
                frame=forecasting_panel(history,survey,outcome=outcome,context_lag=2)
                if exclude_2020:
                    frame=frame.loc[frame.context_year.ne(2020)].copy()
                save_csv(directory/('cohorte_'+name+'.csv'),frame)
                log(f'Evaluando {name}: {int(frame.elegible_prediccion.sum())} filas completas')
                pred,fold=evaluate(frame,name)
                if pred.empty:
                    raise AssertionError(f'Sin folds evaluables: {name}')
                forecasts.append(pred);folds.append(fold)
                if name=='registros_contexto_lag2':
                    primary=frame
            predictions=pd.concat(forecasts,ignore_index=True)
            fold_table=pd.concat(folds,ignore_index=True)
            global_metrics,year_metrics,province_metrics=summarize(predictions)
            comparison=paired_comparison(predictions)
            future=next_year_features(history,survey,year=2025)
            save_csv(directory/'elegibilidad_proyeccion_2025.csv',future)
            future_rows=[]
            model_dir=directory/'modelos_experimentales'
            model_dir.mkdir()
            train=primary.loc[primary.elegible_prediccion]
            test=future.loc[future.features_completas]
            for name in MODEL_NAMES:
                predicted,model=predict_one(train,test,name)
                if not np.isfinite(predicted).all() or (predicted < 0).any():
                    raise AssertionError(f'Proyección inválida: {name}')
                for (_,row),value in zip(test.iterrows(),predicted):
                    future_rows.append({'provincia':row.provincia,'anio':2025,'model':name,'predicted':float(value),
                                        'estado':'RETROSPECTIVO_NO_VALIDADO_2025_INCOMPLETO','publicacion_historica_auditada':False})
                if model is not None:
                    joblib.dump(model,model_dir/(name+'_NO_PRODUCCION.joblib'))
            warning_messages=sorted({str(item.message) for item in caught})
        for name,frame in [('predicciones_fuera_de_tiempo',predictions),('folds',fold_table),('metricas',global_metrics),
                           ('metricas_por_anio',year_metrics),('metricas_por_provincia',province_metrics),
                           ('comparacion_pareada_contexto',comparison),('proyeccion_retrospectiva_2025',pd.DataFrame(future_rows))]:
            save_csv(directory/(name+'.csv'),frame)
        make_figures(directory,crime,panel,global_metrics,predictions)
        results={'eligible_prediction_rows':int(primary.elegible_prediccion.sum()),
                 'descriptive_eligible_pairs':int(panel.elegible_cruce_exploratorio.sum()),
                 'coverage_max_full_year':2024,'out_of_sample_province_years':int(len(predictions.loc[predictions.scenario.eq('registros_contexto_lag2')])/len(MODEL_NAMES)),
                 'future_provinces_eligible':int(future.features_completas.sum()),'warnings':warning_messages}
        write_json(directory/'resumen.json',results)
        write_report(directory,results,panel,future,global_metrics,comparison,fold_table)
        manifest.update(status='COMPLETED',results=results,
                        aggregate_csv_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.glob('*.csv'))})
        log(f'Finalizado. Resultado: {directory / "resultado.md"}')
    except BaseException as error:
        manifest.update(status='FAILED',error=str(error))
        (directory/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
    finally:
        manifest['finished_at']=datetime.now(timezone.utc).isoformat()
        write_json(directory/'manifest.json',manifest)


if __name__=='__main__':
    main()
