"""Paneles agregados reproducibles; no transforma ausencias en ceros."""
import numpy as np
import pandas as pd
from sqlalchemy import text


HOMICIDES_SQL = """
SELECT extract(year from fecha_infraccion)::integer anio, provincia,
       count(*) registros, count(DISTINCT _raw_hash) hashes_distintos,
       count(DISTINCT extract(month from fecha_infraccion)) meses_con_registros,
       min(_clean_run_id) version_clean
FROM clean.homicidio_limpia
WHERE fecha_infraccion IS NOT NULL
GROUP BY 1,2 ORDER BY 1,2
"""

COVERAGE_SQL = """
SELECT anio,count(*) registros,count(DISTINCT mes) meses,
       min(mes) primer_mes,max(mes) ultimo_mes
FROM analitica.v_homicidios GROUP BY anio ORDER BY anio
"""

SURVEY_SQL = """
SELECT anio,provincia,count(*) muestra_registros,
       count(pobreza_binaria) n_pobreza, count(ingreso_per_capita) n_ingreso,
       sum(factor_expansion*pobreza_binaria) /
           nullif(sum(factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL),0) pobreza_ponderada,
       sum(factor_expansion*ingreso_per_capita) /
           nullif(sum(factor_expansion) FILTER(WHERE ingreso_per_capita IS NOT NULL),0) ingreso_ponderado,
       power(sum(factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL),2) /
           nullif(sum(factor_expansion*factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL),0) neff_kish_pobreza,
       count(DISTINCT estrato) estratos_observados,count(DISTINCT upm) upm_observadas,
       count(*) FILTER(WHERE estrato IS NULL OR upm IS NULL) diseno_incompleto,
       sum(factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL) suma_pesos_pobreza,
       min(version_clean) version_clean
FROM analitica.v_enemdu
WHERE mes=12 AND anio BETWEEN 2018 AND 2024 AND apto_contexto_provincia_periodo
GROUP BY anio,provincia ORDER BY anio,provincia
"""


def extract_aggregates(conn):
    """conn debe pertenecer a una transacción READ ONLY del llamador."""
    crime = pd.read_sql(text(HOMICIDES_SQL), conn)
    coverage = pd.read_sql(text(COVERAGE_SQL), conn)
    survey = pd.read_sql(text(SURVEY_SQL), conn)
    provinces = pd.read_sql(text('SELECT codigo_provincia,provincia FROM analitica.v_catalogo_provincias ORDER BY codigo_provincia'), conn)
    return crime, coverage, survey, provinces


def validate_keys(frame, name):
    if frame.duplicated(['provincia', 'anio']).any():
        raise ValueError(f'{name}: más de una fila provincia-año; cruce multiplicaría observaciones')


def validate_survey_aggregates(survey):
    validate_keys(survey, 'encuesta_diciembre')
    if not survey.pobreza_ponderada.dropna().between(0, 1).all():
        raise ValueError('Proporción ponderada fuera de [0,1]')
    if (survey.n_pobreza > survey.muestra_registros).any():
        raise ValueError('Denominador de respuestas mayor que registros')
    if 'neff_kish_pobreza' in survey and (survey.neff_kish_pobreza > survey.n_pobreza + 1e-6).any():
        raise ValueError('Diagnóstico Kish incompatible con el número de respuestas')


def build_history(crime, coverage, provinces, last_year=2024):
    validate_keys(crime, 'homicidios')
    complete = coverage.loc[coverage.meses.eq(12) & coverage.anio.le(last_year), 'anio'].astype(int).tolist()
    if not complete:
        raise ValueError('No hay años con doce meses observados a nivel nacional')
    grid = pd.MultiIndex.from_product([provinces.provincia.tolist(), sorted(complete)],
                                     names=['provincia', 'anio']).to_frame(index=False)
    result = grid.merge(crime, on=['provincia', 'anio'], how='left', validate='one_to_one')
    result['registro_observado'] = result.registros.notna()
    result['ausencia_no_equivale_cero'] = result.registros.isna()
    # Nacionalmente 12 meses es cobertura observada, no certificación de exhaustividad.
    result['doce_meses_nacionales_observados'] = True
    return result


def descriptive_panel(history, survey):
    validate_keys(survey, 'encuesta_diciembre')
    panel = history.loc[history.anio.between(2018, 2024)].merge(
        survey, on=['provincia', 'anio'], how='left', validate='one_to_one', suffixes=('_homicidios', '_enemdu'))
    panel['elegible_cruce_exploratorio'] = panel.registros.notna() & panel.pobreza_ponderada.notna() & panel.ingreso_ponderado.notna()
    panel['motivo_no_elegible'] = np.select(
        [panel.registros.isna(), panel.pobreza_ponderada.isna(), panel.ingreso_ponderado.isna()],
        ['SIN_REGISTROS_OBSERVADOS_NO_ASUMIR_CERO', 'SIN_POBREZA_DICIEMBRE', 'SIN_INGRESO_DICIEMBRE'], default='INCLUIDO')
    panel['dominio_provincial_oficial_verificado'] = False
    return panel


def forecasting_panel(history, survey, outcome='registros', context_lag=2, last_year=2024):
    if context_lag < 1:
        raise ValueError('No usar contexto del mismo año ni del futuro para predecir el año completo')
    validate_keys(history, 'historial')
    validate_keys(survey, 'encuesta')
    result = history.loc[history.anio.between(2020, last_year), ['provincia', 'anio', outcome]].rename(columns={outcome: 'target'}).copy()
    for lag in (1, 2):
        lookup = history[['provincia', 'anio', outcome]].rename(columns={'anio': f'lag_{lag}_year', outcome: f'lag_{lag}'})
        result[f'lag_{lag}_year'] = result.anio - lag
        result = result.merge(lookup, on=['provincia', f'lag_{lag}_year'], how='left', validate='many_to_one')
    result['context_year'] = result.anio - context_lag
    context = survey.rename(columns={'anio': 'context_year'})
    result = result.merge(context, on=['provincia', 'context_year'], how='left', validate='many_to_one')
    return add_features_and_flags(result)


def add_features_and_flags(result):
    result = result.copy()
    for lag in (1, 2):
        result[f'log_lag_{lag}'] = np.log1p(result[f'lag_{lag}'].where(result[f'lag_{lag}'].ge(0)))
    result['tendencia_anio'] = result.anio - 2020
    result['log_ingreso'] = np.log1p(result.ingreso_ponderado.where(result.ingreso_ponderado.ge(0)))
    features = ['log_lag_1', 'log_lag_2', 'pobreza_ponderada', 'log_ingreso']
    result['features_completas'] = result[features].notna().all(axis=1)
    result['elegible_prediccion'] = result.features_completas & result.target.notna()
    result['motivo_no_elegible'] = np.select(
        [result.target.isna(), result.lag_1.isna(), result.lag_2.isna(), result.pobreza_ponderada.isna(), result.log_ingreso.isna()],
        ['TARGET_NO_OBSERVADO_NO_ASUMIR_CERO', 'SIN_ANIO_ANTERIOR', 'SIN_DOS_ANIOS_ANTERIORES',
         'SIN_CONTEXTO_POBREZA_PREVIO', 'SIN_CONTEXTO_INGRESO_PREVIO'], default='INCLUIDO')
    result['fechas_publicacion_verificadas'] = False
    return result


def next_year_features(history, survey, year=2025, outcome='registros', context_lag=2):
    result = pd.DataFrame({'provincia': sorted(history.provincia.unique()), 'anio': year, 'target': np.nan})
    for lag in (1, 2):
        previous = history.loc[history.anio.eq(year-lag), ['provincia', outcome]].rename(columns={outcome: f'lag_{lag}'})
        result[f'lag_{lag}_year'] = year-lag
        result = result.merge(previous, on='provincia', how='left', validate='one_to_one')
    result['context_year'] = year-context_lag
    result = result.merge(survey.rename(columns={'anio': 'context_year'}), on=['provincia', 'context_year'], how='left', validate='many_to_one')
    result = add_features_and_flags(result)
    result['elegible_proyeccion'] = result.features_completas
    result['motivo_proyeccion'] = np.select(
        [result.lag_1.isna(), result.lag_2.isna(), result.pobreza_ponderada.isna(), result.log_ingreso.isna()],
        ['SIN_ANIO_ANTERIOR_COMPLETO', 'SIN_DOS_ANIOS_ANTERIORES', 'SIN_CONTEXTO_POBREZA_PREVIO',
         'SIN_CONTEXTO_INGRESO_PREVIO'], default='FEATURES_COMPLETAS_TARGET_FUTURO_NO_OBSERVADO')
    return result
