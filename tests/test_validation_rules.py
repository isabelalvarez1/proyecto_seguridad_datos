import unittest

from analysis.validation_rules import derived_expressions, ident, literal
from analysis.run_clean_validation import RUN_PATTERN, TARGET_SCHEMA, validation_select


class ValidationPlanTests(unittest.TestCase):
    def test_destination_is_fixed_and_run_id_cannot_inject_sql(self):
        self.assertEqual(TARGET_SCHEMA, "clean_validacion")
        self.assertIsNone(RUN_PATTERN.fullmatch('x;DROP SCHEMA dwh'))
        self.assertIsNone(RUN_PATTERN.fullmatch('../clean'))
        self.assertTrue(RUN_PATTERN.fullmatch('20261015_120000_abcd'))

    def test_identifiers_and_literals_are_escaped(self):
        self.assertEqual(ident('Numeración"x'), '"Numeración""x"')
        self.assertEqual(literal("O'NEIL"), "'O''NEIL'")

    def test_edg_keeps_all_numbering_variants_and_units(self):
        cols = ['Numeracion', 'Numeración', 'Númeración', 'edad', 'cod_edad', 'fecha_fall']
        derived = derived_expressions('edg', cols)
        self.assertIn('v_numeracion_conflicto', derived)
        self.assertIn('"Numeración"', derived['v_numeracion'])
        self.assertIn('"Númeración"', derived['v_numeracion'])
        self.assertIn("'AÑOS'", derived['v_edad_anios'])
        self.assertEqual(cols, ['Numeracion', 'Numeración', 'Númeración', 'edad', 'cod_edad', 'fecha_fall'])

    def test_no_automatic_merging_of_disappearance_status(self):
        derived = derived_expressions('mdi_desaparecido', ['situacion_actual', 'status'])
        self.assertNotIn("THEN 'LOCALIZADO'", derived['v_situacion_actual'])

    def test_enemdu_dpa_ambiguous_does_not_guess_a_name(self):
        derived = derived_expressions('enemdu', ['periodo', 'p03', 'fexp', 'ciudad'])
        self.assertIn('dpa.variantes = 1', derived['v_canton'])
        self.assertIn("'AMBIGUOUS'", derived['v_dpa_estado'])

    def test_chunked_query_keeps_original_columns_and_caches_parsers(self):
        cols = ['periodo', 'p03', 'fexp', 'ciudad']
        query = validation_select('enemdu', 'sample', cols, derived_expressions('enemdu', cols),
                                  "r.ctid < '(100,0)'::tid")
        self.assertIn('normalized AS MATERIALIZED', query)
        self.assertIn('parsed AS MATERIALIZED', query)
        self.assertIn('r."periodo", r."p03", r."fexp", r."ciudad"', query)
        self.assertEqual(query.count('pg_temp.v_period(r."periodo"::text)'), 1)
        self.assertIn("WHERE r.ctid < '(100,0)'::tid", query)


if __name__ == '__main__':
    unittest.main()
