"""Experimento temporal separado de los modelos cargados por la API."""
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


HISTORY_FEATURES = ['log_lag_1', 'log_lag_2', 'tendencia_anio']
CONTEXT_FEATURES = HISTORY_FEATURES + ['pobreza_ponderada', 'log_ingreso']
MODEL_NAMES = ('ultimo_anio', 'promedio_dos_anios', 'poisson_historial', 'poisson_contexto', 'rf_historial', 'rf_contexto')


def pipeline(algorithm, use_context):
    numeric = CONTEXT_FEATURES if use_context else HISTORY_FEATURES
    transformer = ColumnTransformer([
        ('numeric', StandardScaler(), numeric),
        ('province', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['provincia']),
    ], remainder='drop')
    if algorithm == 'poisson':
        estimator = PoissonRegressor(alpha=1.0, max_iter=5000, tol=1e-7)
    elif algorithm == 'rf':
        estimator = RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=5,
                                          random_state=42, n_jobs=1)
    else:
        raise ValueError(algorithm)
    # Sin imputador. Los dos modelos reciben exactamente el mismo universo.
    return Pipeline([('features', transformer), ('model', estimator)])


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if not len(actual) or not np.isfinite(predicted).all() or (predicted < 0).any():
        raise ValueError('Predicciones vacías, no finitas o negativas')
    denominator = actual.sum()
    return {'n': len(actual), 'mae': mean_absolute_error(actual, predicted),
            'rmse': float(np.sqrt(mean_squared_error(actual, predicted))),
            'wape_pct': float(np.abs(actual-predicted).sum()/denominator*100) if denominator else np.nan,
            'r2_secundario': r2_score(actual, predicted) if len(actual)>1 and np.var(actual)>0 else np.nan}


def check_temporal_contract(frame):
    if frame.duplicated(['provincia', 'anio']).any():
        raise AssertionError('Pares provincia-año duplicados')
    for lag in (1, 2):
        if not frame[f'lag_{lag}_year'].eq(frame.anio-lag).all():
            raise AssertionError('Lag no corresponde al año calendario')
    if not frame.context_year.lt(frame.anio).all():
        raise AssertionError('Contexto contemporáneo o futuro: fuga temporal')


def predict_one(train, test, name):
    if name == 'ultimo_anio':
        return test.lag_1.to_numpy(), None
    if name == 'promedio_dos_anios':
        return (test.lag_1.to_numpy()+test.lag_2.to_numpy())/2, None
    algorithm, context = name.split('_', 1)
    fitted = pipeline(algorithm, context == 'contexto')
    fitted.fit(train, train.target)
    return fitted.predict(test), fitted


def evaluate(frame, scenario, min_train_years=2, first_test_year=2022):
    eligible = frame.loc[frame.elegible_prediccion].copy()
    check_temporal_contract(eligible)
    predictions, folds = [], []
    for year in sorted(eligible.loc[eligible.anio.ge(first_test_year), 'anio'].unique()):
        train = eligible.loc[eligible.anio.lt(year)].copy()
        test = eligible.loc[eligible.anio.eq(year)].copy()
        if train.anio.nunique() < min_train_years or len(train)<20 or test.empty:
            folds.append({'scenario': scenario, 'test_year': int(year), 'status': 'SKIPPED_INSUFFICIENT_HISTORY',
                          'n_train': len(train), 'n_test': len(test)})
            continue
        assert train.anio.max() < test.anio.min()
        folds.append({'scenario': scenario, 'test_year': int(year), 'status': 'EVALUATED',
                      'n_train': len(train), 'n_test': len(test), 'train_max_year': int(train.anio.max()),
                      'context_max_test_year': int(test.context_year.max())})
        for name in MODEL_NAMES:
            predicted, _ = predict_one(train, test, name)
            metrics(test.target, predicted)
            for (_, row), value in zip(test.iterrows(), predicted):
                predictions.append({'scenario': scenario, 'model': name, 'provincia': row.provincia,
                                    'anio': int(year), 'actual': float(row.target), 'predicted': float(value),
                                    'train_max_year': int(train.anio.max()), 'context_year': int(row.context_year),
                                    'evaluation_phase': 'HOLDOUT_FINAL_2024' if year == 2024 else 'DEVELOPMENT_TEMPORAL'})
    return pd.DataFrame(predictions), pd.DataFrame(folds)


def summarize(predictions):
    if predictions.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    global_rows, yearly, provincial = [], [], []
    for (scenario, name), group in predictions.groupby(['scenario', 'model']):
        for phase, subset in [('ALL_TEMPORAL', group), ('DEVELOPMENT_2022_2023', group.loc[group.anio.lt(2024)]),
                              ('HOLDOUT_FINAL_2024', group.loc[group.anio.eq(2024)])]:
            if not subset.empty:
                global_rows.append({'scenario': scenario, 'model': name, 'phase': phase,
                                    **metrics(subset.actual, subset.predicted)})
        for year, subset in group.groupby('anio'):
            yearly.append({'scenario': scenario, 'model': name, 'anio': int(year), **metrics(subset.actual, subset.predicted)})
        for province, subset in group.groupby('provincia'):
            provincial.append({'scenario': scenario, 'model': name, 'provincia': province, **metrics(subset.actual, subset.predicted)})
    return pd.DataFrame(global_rows), pd.DataFrame(yearly), pd.DataFrame(provincial)


def paired_comparison(predictions, repetitions=1000):
    """Bootstrap exploratorio por provincia; no cubre incertidumbre ENEMDU/regímenes."""
    rows = []
    rng = np.random.default_rng(42)
    for scenario in predictions.scenario.unique():
        sample = predictions.loc[predictions.scenario.eq(scenario)]
        for algorithm in ('poisson', 'rf'):
            for phase, subset in [('ALL_TEMPORAL', sample), ('HOLDOUT_FINAL_2024', sample.loc[sample.anio.eq(2024)])]:
                h = subset.loc[subset.model.eq(algorithm+'_historial')]
                c = subset.loc[subset.model.eq(algorithm+'_contexto')]
                pair = h.merge(c, on=['provincia', 'anio'], suffixes=('_h', '_c'), validate='one_to_one')
                if pair.empty:
                    continue
                if len(pair) != len(h) or len(pair) != len(c) or not np.array_equal(pair.actual_h, pair.actual_c):
                    raise AssertionError('La comparación no usa las mismas observaciones')
                pair['improvement'] = np.abs(pair.actual_h-pair.predicted_h)-np.abs(pair.actual_c-pair.predicted_c)
                clusters = [g.improvement.to_numpy() for _, g in pair.groupby('provincia')]
                draws = [np.concatenate([clusters[i] for i in rng.integers(0,len(clusters),len(clusters))]).mean()
                         for _ in range(repetitions)]
                rows.append({'scenario': scenario, 'algorithm': algorithm, 'phase': phase,
                             'n_paired': len(pair), 'provinces': len(clusters),
                             'mae_history': float(np.abs(pair.actual_h-pair.predicted_h).mean()),
                             'mae_context': float(np.abs(pair.actual_c-pair.predicted_c).mean()),
                             'improvement_mae_positive_is_better': float(pair.improvement.mean()),
                             'bootstrap_cluster_p025': float(np.quantile(draws,0.025)),
                             'bootstrap_cluster_p975': float(np.quantile(draws,0.975))})
    return pd.DataFrame(rows)
