"""Mart dimensional de consulta, versionado y aditivo al DW histórico."""
DDL = """
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE TABLE IF NOT EXISTS dwh.web_cargas (
    batch_id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.web_estado (
    singleton integer PRIMARY KEY CHECK(singleton=1),
    active_batch_id text NOT NULL REFERENCES dwh.web_cargas(batch_id)
);
CREATE TABLE IF NOT EXISTS dwh.web_dim_tiempo (
    tiempo_key integer PRIMARY KEY, anio integer, mes integer,
    CHECK(mes IS NULL OR mes BETWEEN 1 AND 12)
);
CREATE TABLE IF NOT EXISTS dwh.web_dim_territorio (
    territorio_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provincia text, canton text, provincia_ref text NOT NULL, canton_ref text NOT NULL,
    UNIQUE(provincia_ref,canton_ref)
);
CREATE TABLE IF NOT EXISTS dwh.web_fact_seguridad (
    batch_id text NOT NULL REFERENCES dwh.web_cargas(batch_id) ON DELETE CASCADE,
    fuente text NOT NULL, tiempo_key integer NOT NULL REFERENCES dwh.web_dim_tiempo,
    territorio_key bigint NOT NULL REFERENCES dwh.web_dim_territorio,
    sexo text NOT NULL, grupo_edad text NOT NULL, categoria text NOT NULL,
    registros bigint NOT NULL CHECK(registros>=0),
    cantidad numeric, cantidad_informada bigint NOT NULL,
    duracion_sum numeric, duracion_n bigint NOT NULL,
    PRIMARY KEY(batch_id,fuente,tiempo_key,territorio_key,sexo,grupo_edad,categoria)
);
CREATE INDEX IF NOT EXISTS web_seguridad_filtro ON dwh.web_fact_seguridad(batch_id,fuente,tiempo_key);
CREATE TABLE IF NOT EXISTS dwh.web_fact_contexto (
    batch_id text NOT NULL REFERENCES dwh.web_cargas(batch_id) ON DELETE CASCADE,
    tiempo_key integer NOT NULL REFERENCES dwh.web_dim_tiempo,
    territorio_key bigint NOT NULL REFERENCES dwh.web_dim_territorio,
    registros bigint NOT NULL,pobreza_validos bigint NOT NULL,ingreso_validos bigint NOT NULL,
    pobreza_num numeric,pobreza_den numeric,ingreso_num numeric,ingreso_den numeric,pesos2 numeric,
    PRIMARY KEY(batch_id,tiempo_key,territorio_key)
);
"""

SECURITY_SOURCES = {
    'homicidios': ('v_homicidios', "COALESCE(sexo,CASE WHEN sexo_estado='UNKNOWN' THEN 'NO DETERMINADO' ELSE 'SIN DATO' END)", 'grupo_edad', 'tipo_muerte', 'NULL::numeric', 'NULL::numeric'),
    'armas': ('v_armas', "'NO APLICA'::text", "NULL::text", 'clase_arma', 'cantidad', 'NULL::numeric'),
    'desapariciones': ('v_desapariciones', "COALESCE(sexo,'SIN DATO')", 'grupo_edad', 'situacion_actual', 'NULL::numeric', 'dias_hasta_localizacion'),
    'defunciones': ('v_defunciones', "COALESCE(sexo,'SIN DATO')", 'grupo_edad', 'causa4', 'NULL::numeric', 'NULL::numeric'),
}


def security_sql():
    parts = []
    for source, (view, sex, age, category, quantity, duration) in SECURITY_SOURCES.items():
        parts.append(f"""SELECT '{source}'::text fuente,COALESCE(anio*100+mes,0)::integer tiempo_key,
            provincia,canton,{sex} sexo,COALESCE({age},'SIN DATO') grupo_edad,
            COALESCE({category},'SIN DATO') categoria,count(*)::bigint registros,
            sum({quantity}) cantidad,count({quantity})::bigint cantidad_informada,
            sum({duration}) duracion_sum,count({duration})::bigint duracion_n
            FROM analitica.{view} GROUP BY 1,2,3,4,5,6,7""")
    return ' UNION ALL '.join(parts)


CONTEXT_SQL = """SELECT COALESCE(anio*100+mes,0)::integer tiempo_key,provincia,NULL::text canton,
    count(*)::bigint registros,count(pobreza_binaria)::bigint pobreza_validos,
    count(ingreso_per_capita)::bigint ingreso_validos,
    sum(factor_expansion*pobreza_binaria) pobreza_num,
    sum(factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL) pobreza_den,
    sum(factor_expansion*ingreso_per_capita) ingreso_num,
    sum(factor_expansion) FILTER(WHERE ingreso_per_capita IS NOT NULL) ingreso_den,
    sum(factor_expansion*factor_expansion) FILTER(WHERE pobreza_binaria IS NOT NULL) pesos2
    FROM analitica.v_enemdu GROUP BY 1,2,3"""


def assert_totals(expected, actual):
    if expected != actual:
        raise AssertionError(f'Totales de origen y mart distintos: {expected} != {actual}')
