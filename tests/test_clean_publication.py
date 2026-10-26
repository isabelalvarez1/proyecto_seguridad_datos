import unittest

import pandas as pd

from scripts.clean_edg import clean_edg
from scripts.clean_enemdu import clean_enemdu
from utils.clean_projection import column_mapping, clean_projection, coordinate_contract


class CleanPublicationTests(unittest.TestCase):
    def test_periods_keep_text_months_and_invalid_is_not_invented(self):
        source = pd.DataFrame({'periodo': ['201812.0', 'ene-23', 'dic-20', '202313', None],
                               'p03': ['98 y más', '37', 'No informa', '20', '0']})
        result = clean_enemdu(source)
        self.assertEqual(result.periodo.iloc[:3].tolist(), ['201812', '202301', '202012'])
        self.assertTrue(result.periodo.iloc[3:].isna().all())
        self.assertEqual(result.periodo_original.iloc[1], 'ene-23')
        self.assertTrue(result.edad_censurada.iloc[0])
        self.assertTrue(pd.isna(result.p03.iloc[0]))
        self.assertEqual(result.edad_limite_inferior.iloc[0], 98)
        self.assertEqual(len(source), len(result))

    def test_text_categories_are_not_coerced_to_null(self):
        result = clean_enemdu(pd.DataFrame({'p24': ['Si', 'No', '1.0']}))
        self.assertEqual(result.p24.tolist(), ['SI', 'NO', '1'])

    def test_edg_dates_confirmed_by_components_and_age_units(self):
        source = pd.DataFrame({
            'fecha_fall': ['3/12/2023', '2020-04-03', '3/12/2023'],
            'anio_fall': [2023.0, 2020.0, 2023.0],
            'mes_fall': ['Diciembre', 'Abril', 'Julio'], 'dia_fall': [3, 3, 3],
            'edad': ['12', '35', '999'], 'cod_edad': ['Días', 'Años', 'Sin información'],
            'Numeracion': [1, None, None], 'Numeración': [None, 2, None], 'Númeración': [None, None, 3],
        })
        result = clean_edg(source)
        self.assertEqual(str(result.fecha_fall.iloc[0].date()), '2023-12-03')
        self.assertTrue(pd.isna(result.fecha_fall.iloc[2]))
        self.assertEqual(result.fecha_fall_original.iloc[0], '3/12/2023')
        self.assertTrue(pd.isna(result.edad_anios.iloc[0]))
        self.assertEqual(result.edad_anios.iloc[1], 35)
        self.assertEqual(result.numeracion.tolist(), [1, 2, 3])
        self.assertIn('numeracion__2', result)
        self.assertIn('numeracion__3', result)

    def test_column_collisions_are_preserved(self):
        self.assertEqual(list(column_mapping(['Numeracion', 'Numeración', 'Númeración']).values()),
                         ['numeracion', 'numeracion__2', 'numeracion__3'])

    def test_projection_does_not_confuse_open_age_with_exact_age(self):
        info = [{'column_name': key, 'data_type': 'text'} for key in ['p03', 'periodo', 'ingrl']]
        available = ['v_p03', 'v_p03_estado', 'v_periodo', 'v_periodo_estado', 'v_ingrl', 'v_ingrl_estado']
        expressions, audit = clean_projection('enemdu', info, available)
        self.assertEqual(expressions['p03'], 'r."v_p03"')
        self.assertIn('OPEN_ENDED_98_PLUS', expressions['p03_estado'])
        self.assertIn('NON_NUMERIC_RESPONSE', expressions['ingrl_estado'])
        self.assertIn('p03_original', expressions)
        self.assertTrue(all(item['original_preserved'] for item in audit))

    def test_coordinates_are_not_imputed(self):
        lat, lon, status = coordinate_contract('latitud', 'longitud')
        self.assertIn('THEN', lat)
        self.assertNotIn('COALESCE', lat)
        self.assertIn('ZERO_PAIR', status)
        self.assertIn('OUT_OF_RANGE', status)


if __name__ == '__main__':
    unittest.main()
