import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.exc import DBAPIError

from scripts.run_clean import cleanup_staging_schema


class StagingCleanupTests(unittest.TestCase):
    def test_empty_schema_is_dropped_without_cascade(self):
        conn = MagicMock()
        self.assertEqual(cleanup_staging_schema(conn), 'REMOVED_OR_ALREADY_ABSENT')
        sql = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertIn('DROP SCHEMA IF EXISTS "clean_preparacion" RESTRICT', sql)
        self.assertFalse(any('CASCADE' in statement for statement in sql))

    def test_pending_objects_keep_schema_and_use_savepoint(self):
        conn = MagicMock()
        conn.execute.side_effect = [None, DBAPIError(None, None, SimpleNamespace(pgcode='2BP01'))]
        self.assertEqual(cleanup_staging_schema(conn), 'KEPT_NOT_EMPTY')
        conn.begin_nested.assert_called_once()

    def test_unexpected_database_error_is_not_hidden(self):
        conn = MagicMock()
        error = DBAPIError(None, None, SimpleNamespace(pgcode='42501'))
        conn.execute.side_effect = error
        with self.assertRaises(DBAPIError):
            cleanup_staging_schema(conn)


if __name__ == '__main__':
    unittest.main()
