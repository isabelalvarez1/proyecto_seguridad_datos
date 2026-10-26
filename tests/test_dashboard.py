import math
import os
from decimal import Decimal
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.dashboard import safe, validate_filters, change, dashboard, context
from utils.dashboard_dw import assert_totals
from utils.config import engine


class DashboardUnitTests(unittest.TestCase):
    def test_missing_and_nonfinite_are_not_zero(self):
        self.assertEqual(safe({'value': Decimal('2.5'), 'missing': None, 'invalid': math.nan}),
                         {'value': 2.5, 'missing': None, 'invalid': None})
        self.assertIsNone(change(5, 0))
        self.assertIsNone(change(None, 5))

    def test_shared_filter_contract_rejects_invalid_ranges_and_provinces(self):
        with self.assertRaises(HTTPException): validate_filters(2025, 2024, [])
        with self.assertRaises(HTTPException): validate_filters(2024, 2024, ['INVALIDA'])
        with self.assertRaises(HTTPException): validate_filters(2024, 2024, ['GUAYAS','AZUAY','LOJA','MANABÍ','EL ORO'])
        self.assertEqual(validate_filters(2024, 2024, ['GUAYAS','GUAYAS']), ['GUAYAS'])

    def test_dw_validation_prevents_silent_loss(self):
        with self.assertRaises(AssertionError): assert_totals(100, 99)
        assert_totals(100, 100)


@unittest.skipUnless(os.environ.get('DASHBOARD_INTEGRATION') == '1', 'Requiere PostgreSQL y mart web preparado')
class DashboardIntegrationTests(unittest.TestCase):
    def test_successful_refresh_is_idempotent_and_keeps_previous_batch(self):
        from scripts.refresh_dashboard import refresh
        with engine.connect() as conn:
            previous = conn.execute(text('SELECT active_batch_id FROM dwh.web_estado')).scalar_one()
            counts = conn.execute(text('SELECT metadata FROM dwh.web_cargas WHERE batch_id=:b'), {'b': previous}).scalar_one()['source_counts']
        batch, metadata = refresh()
        self.assertNotEqual(batch, previous)
        self.assertEqual(counts, metadata['source_counts'])
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT active_batch_id FROM dwh.web_estado')).scalar_one(), batch)
            retained = conn.execute(text('SELECT batch_id FROM dwh.web_cargas')).scalars().all()
        self.assertIn(previous, retained)
        self.assertLessEqual(len(retained), 2)

    def test_security_donut_and_time_totals_match_analytic_source(self):
        data = dashboard('homicidios', 2024, 2024, ['GUAYAS'], 'annual', 'monthly')
        with engine.connect() as conn:
            expected = conn.execute(text("SELECT count(*) FROM analitica.v_homicidios WHERE anio=2024 AND provincia='GUAYAS'")).scalar_one()
        self.assertEqual(data['totals']['registros'], expected)
        self.assertEqual(sum(item['registros'] for item in data['sexes']), expected)
        self.assertEqual(sum(item['registros'] for item in data['heatmap']), expected)
        self.assertEqual(sum(item['registros'] for item in data['territories']), expected)
        self.assertEqual(sum(item['registros'] for item in data['categories']), expected)

    def test_context_is_ratio_of_sums_not_mean_of_percentages(self):
        data = context(2024, 2024, ['GUAYAS'])['data'][0]
        with engine.connect() as conn:
            value = conn.execute(text("""SELECT sum(factor_expansion*pobreza_binaria)/
                sum(factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL)*100
                FROM analitica.v_enemdu WHERE anio=2024 AND mes=12 AND provincia='GUAYAS'""")).scalar_one()
        self.assertAlmostEqual(data['pobreza_pct'], float(value), places=8)

    def test_missing_quantity_and_partial_year_comparison(self):
        data = dashboard('armas', 2025, 2025, [], 'annual', 'annual')
        self.assertIsNone(data['totals']['cantidad'])
        self.assertEqual(data['totals']['cantidad_informada'], 0)
        self.assertEqual(data['comparison']['months'], list(range(1,12)))

    def test_failed_refresh_preserves_active_batch(self):
        from scripts.refresh_dashboard import refresh
        with engine.connect() as conn:
            before = conn.execute(text('SELECT active_batch_id FROM dwh.web_estado')).scalar_one()
        with patch('scripts.refresh_dashboard.security_sql', return_value='SELECT * FROM __dashboard_failure_probe_missing'):
            with self.assertRaises(DBAPIError): refresh()
        with engine.connect() as conn:
            after = conn.execute(text('SELECT active_batch_id FROM dwh.web_estado')).scalar_one()
        self.assertEqual(before, after)

    def test_managed_views_rebind_with_stable_identity_and_rollback(self):
        from scripts.create_analytic_views import bind_views
        import uuid
        suffix = uuid.uuid4().hex[:10]
        conn = engine.connect(); transaction = conn.begin()
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('proyecto_ecuador_clean_publication'))"))
            oid = conn.execute(text("SELECT 'analitica.v_homicidios'::regclass::oid")).scalar_one()
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS clean_preparacion'))
            conn.execute(text(f'CREATE TABLE clean_preparacion.probe_{suffix} AS SELECT * FROM clean.homicidio_limpia WHERE FALSE'))
            conn.execute(text(f'ALTER TABLE clean.homicidio_limpia RENAME TO probe_old_{suffix}'))
            conn.execute(text(f'ALTER TABLE clean_preparacion.probe_{suffix} SET SCHEMA clean'))
            conn.execute(text(f'ALTER TABLE clean.probe_{suffix} RENAME TO homicidio_limpia'))
            bind_views(conn)
            self.assertEqual(conn.execute(text('SELECT count(*) FROM analitica.v_homicidios')).scalar_one(), 0)
            self.assertEqual(conn.execute(text("SELECT 'analitica.v_homicidios'::regclass::oid")).scalar_one(), oid)
        finally:
            transaction.rollback(); conn.close()
        with engine.connect() as conn:
            self.assertGreater(conn.execute(text('SELECT count(*) FROM analitica.v_homicidios')).scalar_one(), 0)

    def test_raw_swap_keeps_previous_table_and_can_rollback(self):
        from scripts.load_raw import publish_raw
        import uuid
        schema = 'raw_probe_' + uuid.uuid4().hex[:8]
        conn = engine.connect(); transaction = conn.begin()
        try:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'CREATE TABLE {schema}.source AS SELECT 1 AS value'))
            conn.execute(text(f'CREATE TABLE {schema}.staging AS SELECT * FROM (VALUES(1),(2)) t(value)'))
            old_oid = conn.execute(text('SELECT to_regclass(:name)::oid'), {'name': schema + '.source'}).scalar_one()
            publish_raw(conn, 'staging', 'source', schema)
            self.assertEqual(conn.execute(text(f'SELECT count(*) FROM {schema}.source')).scalar_one(), 2)
            old_schema = conn.execute(text('SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=:o'), {'o': old_oid}).scalar_one()
            self.assertEqual(old_schema, 'raw_historial')
        finally:
            transaction.rollback(); conn.close()
