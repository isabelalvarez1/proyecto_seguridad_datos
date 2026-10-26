"""Ensayo SQL del contrato clean con muestras, sin tablas persistentes."""
from sqlalchemy import text

from analysis.run_clean_validation import columns
from scripts.run_clean import load_validation, projection_sql
from utils.clean_projection import clean_projection, coordinate_contract
from utils.config import engine
from utils.validation_sql import SOURCES, ident


def main():
    validation = load_validation('validacion_20261016_01')
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text('SET LOCAL jit=off'))
        for source in SOURCES:
            source_table = validation['completed_sources'][source]
            schema, table = source_table.split('.')
            info = columns(conn, 'raw', source)
            available = [item['column_name'] for item in columns(conn, schema, table)]
            expressions, audit = clean_projection(source, info, available)
            query = projection_sql(source_table, info, expressions, 'sample', "r.ctid < '(30,0)'::tid")
            original_fields = [ident(item['clean_column'] + '_original' if item['original_preserved'] else item['clean_column'])
                               for item in audit]
            record = 'ROW(' + ', '.join(original_fields) + ')::text'
            row = conn.execute(text(f'SELECT count(*) n,count(*) FILTER(WHERE md5({record})<>_raw_hash) wrong '
                                    f'FROM ({query}) sample')).one()
            assert row.n > 0 and row.wrong == 0, (source, row)
            print(source, 'filas de ensayo', row.n, 'originales alterados', row.wrong)
        lat, lon, state = coordinate_contract('latitud', 'longitud')
        for a, b, expected in [(0, 0, 'ZERO_PAIR'), (-1, -90, 'OBSERVED_NOT_IMPUTED'),
                               (None, -78, 'MISSING_OR_UNRESOLVED_PAIR'), (1, 500, 'OUT_OF_RANGE')]:
            row = conn.execute(text(f'SELECT {lat} lat,{lon} lon,{state} state '
                                    'FROM (SELECT CAST(:a AS numeric) v_latitud,CAST(:b AS numeric) v_longitud) r'),
                               {'a': a, 'b': b}).one()
            assert row.state == expected, row
            if expected != 'OBSERVED_NOT_IMPUTED':
                assert row.lat is None and row.lon is None, row
        print('OK: proyecciones de las cinco fuentes y pares geográficos verificados en solo lectura.')


if __name__ == '__main__':
    main()
