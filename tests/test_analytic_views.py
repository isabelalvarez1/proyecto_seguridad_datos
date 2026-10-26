import unittest

from scripts.create_analytic_views import excluded_reason
from utils.analytic_views import VIEWS, definitions, catalog_sql


class AnalyticViewTests(unittest.TestCase):
    def test_views_are_selection_queries_without_materialization_or_dml(self):
        for name, query in definitions().items():
            with self.subTest(view=name):
                self.assertTrue(query.lstrip().startswith('SELECT'))
                self.assertNotIn('SELECT *', query)
                for keyword in ('INSERT INTO', 'DELETE FROM', 'UPDATE ', 'TRUNCATE ', 'REFRESH ', 'MATERIALIZED VIEW'):
                    self.assertNotIn(keyword, query.upper())

    def test_projection_omits_identifiers_and_copies_but_keeps_survey_design(self):
        for view in VIEWS:
            names = [field.name for field in view.fields]
            self.assertEqual(len(names), len(set(names)))
            self.assertFalse(any(name.startswith('numeracion') or name.endswith('_original') for name in names))
            self.assertFalse(any(name in names for name in ('id_persona', 'id_hogar', 'id_vivienda', '_raw_hash')))
        survey = next(view for view in VIEWS if view.name == 'v_enemdu')
        roles = {field.name: field.role for field in survey.fields}
        self.assertEqual(roles['factor_expansion'], 'diseno_muestral')
        self.assertEqual(roles['estrato'], 'diseno_muestral')
        self.assertEqual(roles['upm'], 'diseno_muestral')

    def test_null_poverty_is_not_changed_to_non_poor(self):
        survey = next(view for view in VIEWS if view.name == 'v_enemdu')
        field = next(field for field in survey.fields if field.name == 'pobreza_binaria')
        self.assertIn("WHEN c.pobreza='NO POBRE' THEN 0", field.sql)
        self.assertNotIn('ELSE 0', field.sql)

    def test_province_lookup_requires_unique_reference(self):
        self.assertIn('HAVING count(DISTINCT', catalog_sql())
        self.assertIn(')=1', catalog_sql())
        self.assertNotIn('DISTINCT ON', catalog_sql())

    def test_high_missingness_does_not_mean_delete_for_every_subgroup(self):
        decision, reason = excluded_reason('mor_mat', 200, 700000)
        self.assertEqual(decision, 'UNIVERSO_ESPECIFICO')
        self.assertIn('no excluir por nulos globales', reason)
        self.assertEqual(excluded_reason('sin_valores', 0, 100)[0], 'EXCLUIDA_SIN_VALORES')

    def test_redundancy_and_audit_controls_have_explicit_reasons(self):
        self.assertEqual(excluded_reason('p03', 100, 100)[0], 'REEMPLAZADA_POR_DERIVADA')
        self.assertEqual(excluded_reason('anio_fall', 100, 100)[0], 'PARTES_FECHA_AUDITORIA')
        self.assertEqual(excluded_reason('causa103', 100, 100)[0], 'AGRUPACION_ALTERNATIVA')
        self.assertEqual(excluded_reason('fecha_fall_estado', 100, 100)[0], 'CONTROL_NO_PUBLICADO')


if __name__ == '__main__':
    unittest.main()
