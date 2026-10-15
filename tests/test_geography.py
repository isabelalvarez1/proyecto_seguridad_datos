import unittest
from unittest.mock import patch

import pandas as pd

from utils.cleaning import canonical_canton, canonical_provincia
from utils.dwh_helpers import dpa_from_codigos


class GeographyTests(unittest.TestCase):
    def test_duran_variants_share_the_same_name(self):
        for value in ("DURAN", "DURÁN", "  Durán  "):
            with self.subTest(value=value):
                self.assertEqual(canonical_canton(value), "DURÁN")

    def test_province_aliases_and_missing_values(self):
        self.assertEqual(canonical_provincia(" STO DGO DE LOS TSÁCHILAS "),
                         "SANTO DOMINGO DE LOS TSÁCHILAS")
        self.assertEqual(canonical_provincia("GALAPAGOS"), "GALÁPAGOS")
        self.assertIsNone(canonical_provincia(pd.NA))

    def test_dpa_fallback_preserves_chunk_index(self):
        catalog = pd.DataFrame({
            "codigo_canton": ["0101"],
            "codigo_provincia": ["01"],
            "nombre_canton": ["CUENCA"],
            "nombre_provincia": ["AZUAY"],
        })
        # Un segundo chunk no empieza en cero. El respaldo debe alinearse
        # por posición, no perderse por una unión de índices 0 vs. 50000.
        codes = pd.Series(["010101", "999999", None, "SIN_DATO"],
                          index=[50000, 50001, 50002, 50003])
        with patch("utils.dwh_helpers.dpa_lookup", return_value=catalog):
            result = dpa_from_codigos(codes)
        self.assertTrue(result.index.equals(codes.index))
        self.assertEqual(result.loc[50000, "provincia_join"], "AZUAY")
        self.assertEqual(result.loc[50001, "codigo_provincia_join"], "99")
        self.assertTrue(pd.isna(result.loc[50001, "provincia_join"]))
        self.assertTrue(result.loc[[50002, 50003], "provincia_join"].isna().all())
        self.assertTrue(result.loc[[50002, 50003], "codigo_provincia_join"].isna().all())


if __name__ == "__main__":
    unittest.main()
