"""Compatibilidad de los análisis existentes con las reglas compartidas."""
from utils.validation_sql import (
    TARGET_SCHEMA, SOURCES, MISSING, UNKNOWN, NOT_APPLICABLE, TEMP_FUNCTIONS,
    ident, literal, sql_list, norm, missing_state, meaningful,
    canonical_province, canonical_canton, derived_expressions, dpa_join,
)
