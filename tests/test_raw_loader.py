from pathlib import Path
import unittest

from scripts.load_raw import read_csv_robusto, file_digest


class RawLoaderTests(unittest.TestCase):
    def test_separator_is_verified_before_returning_reader(self):
        path = Path(__file__).parent/'fixtures'/'raw_semicolon.csv'
        result = read_csv_robusto(path)
        self.assertEqual(result.columns.tolist(), ['periodo', 'sexo', 'ingreso'])
        self.assertEqual(len(result), 2)
        with read_csv_robusto(path, chunksize=1) as reader:
            chunk = next(reader)
            self.assertEqual(chunk.periodo.iloc[0], 'ene-26')

    def test_file_fingerprint_is_stable(self):
        path = Path(__file__).parent/'fixtures'/'raw_semicolon.csv'
        self.assertEqual(file_digest(path), file_digest(path))
        self.assertEqual(len(file_digest(path)), 64)
