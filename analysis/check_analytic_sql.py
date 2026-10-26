"""Ensayo de selección y derivaciones con solo SELECT, sin crear vistas."""
from sqlalchemy import text

from utils.analytic_views import VIEWS, catalog_sql
from utils.config import engine


def field(view_name, name):
    return next(field for view in VIEWS if view.name == view_name for field in view.fields if field.name == name).sql


def main():
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text('SET LOCAL jit=off'))
        for view in VIEWS:
            query = view.sql.replace('analitica.v_catalogo_provincias', '(' + catalog_sql() + ')')
            query += " WHERE c.ctid < '(40,0)'::tid"
            count = conn.execute(text('SELECT count(*) FROM (' + query + ') sample')).scalar_one()
            assert count > 0, view.name
            print(view.name, 'SQL válido y filas de ensayo', count)
        poverty = field('v_enemdu', 'pobreza_binaria')
        for value, expected in [(None, None), ('POBRE', 1), ('NO POBRE', 0), ('SIN_DATO', None)]:
            actual = conn.execute(text(f'SELECT {poverty} FROM (SELECT CAST(:p AS text) pobreza) c'), {'p': value}).scalar_one()
            assert actual == expected, (value, actual)
        group = field('v_enemdu', 'grupo_edad')
        actual = conn.execute(text(f'SELECT {group} FROM (SELECT NULL::numeric edad_anios,TRUE edad_censurada,98::numeric edad_limite_inferior) c')).scalar_one()
        assert actual == '65+', actual
        duration = field('v_desapariciones', 'dias_hasta_localizacion')
        origin = field('v_desapariciones', 'duracion_origen')
        for start, end, expected in [('2025-01-01', '2025-01-03', 2), ('2025-01-03', '2025-01-01', None), ('2025-01-01', None, None)]:
            row = conn.execute(text(f'SELECT {duration} dias,{origin} origen FROM '
                                    '(SELECT CAST(:a AS date) fecha_desaparicion,CAST(:b AS date) fecha_localizacion,NULL::numeric dias_solucion) c'),
                               {'a': start, 'b': end}).one()
            assert row.dias == expected, row
            assert row.origen == ('CALCULADA_FECHAS' if expected is not None else 'NO_OBSERVABLE'), row
        interpretation = field('v_defunciones', 'autopsia_interpretada')
        for value, expected in [('9.0', None), ('1.0', None), ('SI', 'SI'), ('NO', 'NO'), (None, None)]:
            actual = conn.execute(text(f'SELECT {interpretation} FROM (SELECT CAST(:a AS text) autopsia) c'), {'a': value}).scalar_one()
            assert actual == expected, (value, actual)
        group = field('v_defunciones', 'grupo_edad')
        for value, unit, expected in [(5, 'MESES', 'MENOR_DE_1_AÑO'), (20, 'DÍAS', 'MENOR_DE_1_AÑO'), (999, None, None)]:
            actual = conn.execute(text(f'SELECT {group} FROM '
                                       '(SELECT CAST(:age AS numeric) edad,CAST(:unit AS text) cod_edad,NULL::numeric edad_anios) c'),
                                  {'age': value, 'unit': unit}).scalar_one()
            assert actual == expected, (value, unit, actual)
    print('OK: derivaciones observadas y ausencia de imputaciones arbitrarias verificadas.')


if __name__ == '__main__':
    main()
