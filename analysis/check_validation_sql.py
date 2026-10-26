"""Regresión SQL con funciones de sesión; no crea tablas persistentes."""
from sqlalchemy import text

from analysis.validation_rules import TEMP_FUNCTIONS, missing_state
from utils.config import engine


def main():
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(TEMP_FUNCTIONS))
            cases = [
                ('v_period', '201812.0', '201812'),
                ('v_period', ' ene-23 ', '202301'),
                ('v_period', 'dic-20', '202012'),
                ('v_period', '202313', None),
                ('v_period', 'SIN_DATO', None),
                ('v_period', None, None),
                ('v_date', '2020/02/29', '2020-02-29'),
                ('v_date', '2020-04-03 00:00:00', '2020-04-03'),
                ('v_date', '20200229', '2020-02-29'),
                ('v_date', '2021/02/29', None),
                ('v_date', '9999/99/99', None),
                ('v_date', '03/04/2020', None),
                ('v_date', 'NO_APLICA', None),
                ('v_number', '123,45', '123.45'),
                ('v_number', 'SIN_DATO', None),
                ('v_number', '1,000.25', None),
            ]
            for function, value, expected in cases:
                actual = conn.execute(text(f'SELECT pg_temp.{function}(:v)::text'), {'v': value}).scalar_one()
                assert actual == expected, (function, value, actual, expected)
            for value, expected in [(None, 'SQL_NULL'), ('  ', 'EMPTY_OR_SENTINEL'),
                                    ('Sin información', 'UNKNOWN'), ('NO_APLICA', 'NOT_APPLICABLE'),
                                    ('NO', 'PRESENT'), ('0', 'PRESENT')]:
                # Referencia a una columna tipada, no interpolar valores en SQL.
                actual = conn.execute(text('SELECT ' + missing_state('value') +
                                          ' FROM (SELECT CAST(:v AS text) value) q'), {'v': value}).scalar_one()
                assert actual == expected, (value, actual, expected)
            actual = conn.execute(text("SELECT pg_temp.v_code('90150.0',6)")).scalar_one()
            assert actual == '090150', actual
            confirmed = [
                ('3/12/2023', '2023.0', 'Diciembre', '3.0', '2023-12-03'),
                ('26/3/2023', '2023', 'Marzo', '26', '2023-03-26'),
                ('3/12/2023', '2023', 'Julio', '3', None),
                ('29/2/2023', '2023', 'Febrero', '29', None),
                ('9999/99/99', '9999', '99', '99', None),
                ('3/12/2023', None, None, None, None),
            ]
            for value, yy, mm, dd, expected in confirmed:
                actual = conn.execute(text('SELECT pg_temp.v_edg_date(:v,:y,:m,:d)::text'),
                                      {'v': value, 'y': yy, 'm': mm, 'd': dd}).scalar_one()
                assert actual == expected, (value, yy, mm, dd, actual, expected)
            print(f'OK: {len(cases) + 7 + len(confirmed)} regresiones SQL; transacción revertida.')
        finally:
            transaction.rollback()


if __name__ == '__main__':
    main()
