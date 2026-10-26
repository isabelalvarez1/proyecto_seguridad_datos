import unittest

import numpy as np
import pandas as pd

from analysis.provincial_panel import build_history, forecasting_panel, descriptive_panel, next_year_features, validate_survey_aggregates
from ml.provincial_evaluation import check_temporal_contract, evaluate, metrics, predict_one


def fixtures():
    crime=pd.DataFrame([{'provincia':p,'anio':y,'registros':20+(y-2014)*3+i,
                         'hashes_distintos':19+(y-2014)*3+i,'meses_con_registros':12}
                        for i,p in enumerate(['A','B']) for y in range(2014,2025)])
    coverage=pd.DataFrame({'anio':list(range(2014,2026)), 'meses':[12]*11+[11]})
    provinces=pd.DataFrame({'provincia':['A','B']})
    survey=pd.DataFrame([{'provincia':p,'anio':y,'pobreza_ponderada':0.2+0.01*i,
                          'ingreso_ponderado':200+y-2018+i,'n_pobreza':100,'muestra_registros':102}
                         for i,p in enumerate(['A','B']) for y in range(2018,2025)])
    return crime,coverage,provinces,survey


class ProvincialStudyTests(unittest.TestCase):
    def test_missing_province_year_is_not_zero_and_partial_year_is_excluded(self):
        crime,coverage,provinces,_=fixtures()
        crime=crime.loc[~(crime.provincia.eq('B') & crime.anio.eq(2019))]
        history=build_history(crime,coverage,provinces)
        row=history.loc[history.provincia.eq('B') & history.anio.eq(2019)].iloc[0]
        self.assertTrue(pd.isna(row.registros))
        self.assertTrue(row.ausencia_no_equivale_cero)
        self.assertNotIn(2025,history.anio.tolist())

    def test_lags_are_calendar_joins_not_shifts_across_missing_years(self):
        crime,coverage,provinces,survey=fixtures()
        history=build_history(crime,coverage,provinces)
        history.loc[history.provincia.eq('A') & history.anio.eq(2021),'registros']=np.nan
        panel=forecasting_panel(history,survey)
        row=panel.loc[panel.provincia.eq('A') & panel.anio.eq(2022)].iloc[0]
        self.assertTrue(pd.isna(row.lag_1))
        self.assertEqual(row.context_year,2020)
        self.assertFalse(row.elegible_prediccion)

    def test_future_target_perturbation_does_not_change_past_features(self):
        crime,coverage,provinces,survey=fixtures()
        history=build_history(crime,coverage,provinces)
        original=forecasting_panel(history,survey)
        changed=history.copy()
        changed.loc[changed.anio.eq(2024),'registros']=1000000
        new=forecasting_panel(changed,survey)
        columns=['provincia','anio','log_lag_1','log_lag_2','pobreza_ponderada','log_ingreso']
        pd.testing.assert_frame_equal(original[columns],new[columns])

    def test_contemporaneous_context_and_duplicate_keys_are_rejected(self):
        crime,coverage,provinces,survey=fixtures()
        history=build_history(crime,coverage,provinces)
        with self.assertRaises(ValueError):
            forecasting_panel(history,survey,context_lag=0)
        with self.assertRaises(ValueError):
            descriptive_panel(history,pd.concat([survey,survey.iloc[:1]]))

    def test_declared_lag_contract_detects_leakage(self):
        crime,coverage,provinces,survey=fixtures()
        panel=forecasting_panel(build_history(crime,coverage,provinces),survey)
        panel['context_year']=panel.anio
        with self.assertRaises(AssertionError):
            check_temporal_contract(panel)

    def test_test_target_is_not_a_predictor(self):
        crime,coverage,provinces,survey=fixtures()
        panel=forecasting_panel(build_history(crime,coverage,provinces),survey)
        panel=panel.loc[panel.elegible_prediccion]
        train=panel.loc[panel.anio.lt(2024)]
        test=panel.loc[panel.anio.eq(2024)].copy()
        a,_=predict_one(train,test,'poisson_contexto')
        test['target']=99999999
        b,_=predict_one(train,test,'poisson_contexto')
        np.testing.assert_allclose(a,b)

    def test_metrics_and_last_year_reference(self):
        self.assertEqual(metrics([10,20],[10,20])['mae'],0)
        with self.assertRaises(ValueError):
            metrics([10],[np.nan])
        reference,_=predict_one(None,pd.DataFrame({'lag_1':[4,8]}),'ultimo_anio')
        self.assertEqual(reference.tolist(),[4,8])

    def test_expanding_folds_are_strictly_prior_and_models_share_test_rows(self):
        crime,coverage,provinces,survey=fixtures()
        base=forecasting_panel(build_history(crime,coverage,provinces),survey)
        one=base.loc[base.provincia.eq('A')]
        panel=pd.concat([one.assign(provincia='P'+str(i)) for i in range(10)],ignore_index=True)
        predictions,folds=evaluate(panel,'synthetic')
        self.assertEqual(folds.test_year.tolist(),[2022,2023,2024])
        self.assertTrue((folds.train_max_year<folds.test_year).all())
        counts=predictions.groupby(['model','anio']).size()
        self.assertTrue(counts.eq(10).all())
        self.assertTrue(predictions.loc[predictions.anio.eq(2024),'evaluation_phase'].eq('HOLDOUT_FINAL_2024').all())

    def test_future_projection_eligibility_is_distinct_from_known_target(self):
        crime,coverage,provinces,survey=fixtures()
        history=build_history(crime,coverage,provinces)
        future=next_year_features(history,survey)
        self.assertTrue(future.elegible_proyeccion.all())
        self.assertFalse(future.elegible_prediccion.any())
        self.assertTrue(future.target.isna().all())
        history.loc[history.provincia.eq('B') & history.anio.eq(2024),'registros']=np.nan
        future=next_year_features(history,survey)
        self.assertEqual(future.loc[future.provincia.eq('B'),'motivo_proyeccion'].iloc[0],'SIN_ANIO_ANTERIOR_COMPLETO')

    def test_invalid_survey_proportion_is_rejected(self):
        _,_,_,survey=fixtures()
        validate_survey_aggregates(survey)
        survey.loc[0,'pobreza_ponderada']=1.5
        with self.assertRaises(ValueError):
            validate_survey_aggregates(survey)


if __name__=='__main__':
    unittest.main()
