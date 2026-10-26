"""Reglas PostgreSQL compartidas por validación y publicación de clean.

Las funciones SQL se crean únicamente en pg_temp. Ninguna regla escribe en
raw, clean o dwh. Los originales permanecen en cada tabla de validación.
"""

from utils.cleaning import PROVINCIAS_ALIASES, PROVINCIAS_CANONICAS


TARGET_SCHEMA = "clean_validacion"
SOURCES = {
    "mdi_homicidio": "homicidio_limpia",
    "mdi_arma": "mdi_arma_limpia",
    "mdi_desaparecido": "mdi_desaparecido_limpia",
    "edg": "edg_limpia",
    "enemdu": "enemdu_limpia",
}

MISSING = ("", "NAN", "NONE", "NULL", "NA", "N/A", "N.A", "<NA>",
           "SIN_DATO", "SIN DATO", "SIN DATOS", "S/D", "SD", "-", "--", "---", ".", "..", "...")
UNKNOWN = ("SIN INFORMACIÓN", "SIN INFORMACION", "NO DETERMINADO", "NO DETERMINADA",
           "SE IGNORA", "IGNORADO", "DESCONOCIDO", "DESCONOCIDA")
NOT_APPLICABLE = ("NO_APLICA", "NO APLICA")


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def sql_list(values):
    return ", ".join(literal(value) for value in values)


def norm(expression):
    return f"upper(btrim(regexp_replace({expression}::text, '\\s+', ' ', 'g')))"


def missing_state(expression):
    value = norm(expression)
    return (f"CASE WHEN {expression} IS NULL THEN 'SQL_NULL' "
            f"WHEN {value} IN ({sql_list(MISSING)}) THEN 'EMPTY_OR_SENTINEL' "
            f"WHEN {value} IN ({sql_list(UNKNOWN)}) THEN 'UNKNOWN' "
            f"WHEN {value} IN ({sql_list(NOT_APPLICABLE)}) THEN 'NOT_APPLICABLE' "
            "ELSE 'PRESENT' END")


def meaningful(expression):
    return f"({missing_state(expression)}) = 'PRESENT'"


def canonical_province(expression):
    # Comparación con variantes con y sin tildes, sin necesitar extensiones PG.
    key = f"translate({norm(expression)}, 'ÁÉÍÓÚÜÑ', 'AEIOUUN')"
    pairs = dict(PROVINCIAS_CANONICAS)
    pairs.update({alias: PROVINCIAS_CANONICAS[target]
                  for alias, target in PROVINCIAS_ALIASES.items()})
    cases = " ".join(f"WHEN {literal(k)} THEN {literal(v)}" for k, v in pairs.items())
    return f"CASE WHEN {meaningful(expression)} THEN CASE {key} {cases} ELSE {norm(expression)} END END"


def canonical_canton(expression):
    return (f"CASE WHEN {meaningful(expression)} THEN CASE WHEN "
            f"translate({norm(expression)}, 'ÁÉÍÓÚÜÑ', 'AEIOUUN') = 'DURAN' "
            f"THEN 'DURÁN' ELSE {norm(expression)} END END")


# No interpretar códigos 1/2/9 de categorías sin su diccionario.
# Fechas ambiguas con año al final se dejan pendientes, no se adivinan.
TEMP_FUNCTIONS = r"""
CREATE OR REPLACE FUNCTION pg_temp.v_number(value text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v text;
BEGIN
    v := btrim(value);
    IF v IS NULL OR length(v) > 80 THEN RETURN NULL; END IF;
    IF v ~ '^[+-]?[0-9]+,[0-9]+$' THEN v := replace(v, ',', '.'); END IF;
    IF v !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
    THEN RETURN NULL; END IF;
    RETURN v::numeric;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION pg_temp.v_period(value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v text; yy integer; mm integer;
BEGIN
    v := upper(btrim(value));
    IF v ~ '^[0-9]{6}([.]0+)?$' THEN
        v := left(v, 6); yy := left(v, 4)::integer; mm := right(v, 2)::integer;
    ELSIF v ~ '^(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)-[0-9]{2}$' THEN
        yy := 2000 + right(v, 2)::integer;
        mm := array_position(ARRAY['ENE','FEB','MAR','ABR','MAY','JUN',
                                   'JUL','AGO','SEP','OCT','NOV','DIC'], left(v, 3));
    ELSE RETURN NULL;
    END IF;
    IF yy NOT BETWEEN 1900 AND 2099 OR mm NOT BETWEEN 1 AND 12 THEN RETURN NULL; END IF;
    RETURN yy::text || lpad(mm::text, 2, '0');
END $$;

CREATE OR REPLACE FUNCTION pg_temp.v_date(value text) RETURNS date
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v text; yy integer; mm integer; dd integer; parts text[];
BEGIN
    v := btrim(value);
    IF v IS NULL THEN RETURN NULL; END IF;
    -- Admite fecha ISO con hora de origen; no usa DateStyle del servidor.
    IF v ~ '^[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}([ T][0-9:.]+)?$' THEN
        parts := regexp_split_to_array(split_part(replace(v, 'T', ' '), ' ', 1), '[-/]');
        yy := parts[1]::integer; mm := parts[2]::integer; dd := parts[3]::integer;
    ELSIF v ~ '^[0-9]{8}$' THEN
        yy := left(v, 4)::integer; mm := substring(v, 5, 2)::integer; dd := right(v, 2)::integer;
    ELSE RETURN NULL;
    END IF;
    RETURN make_date(yy, mm, dd);
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION pg_temp.v_code(value text, width integer) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN btrim(value) ~ ('^[0-9]{1,' || width || '}([.]0+)?$')
                THEN lpad(regexp_replace(btrim(value), '[.]0+$', ''), width, '0') END
$$;

CREATE OR REPLACE FUNCTION pg_temp.v_edg_date(value text, year_part text, month_part text, day_part text)
RETURNS date LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE direct date; yy numeric; mm numeric; dd numeric; v text; candidate date; parts text[];
BEGIN
    direct := pg_temp.v_date(value);
    IF direct IS NOT NULL THEN RETURN direct; END IF;
    -- Interpretar día/mes/año solo si las tres columnas de origen lo confirman.
    v := btrim(value);
    IF v IS NULL OR v !~ '^[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4}$' THEN RETURN NULL; END IF;
    yy := pg_temp.v_number(year_part); dd := pg_temp.v_number(day_part);
    mm := pg_temp.v_number(month_part);
    IF mm IS NULL THEN
        mm := array_position(ARRAY['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO',
                                  'JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE'],
                             upper(btrim(month_part)));
        IF upper(btrim(month_part)) = 'SETIEMBRE' THEN mm := 9; END IF;
    END IF;
    IF yy IS NULL OR mm IS NULL OR dd IS NULL OR yy <> trunc(yy) OR mm <> trunc(mm)
       OR dd <> trunc(dd) OR yy NOT BETWEEN 1 AND 9999 THEN RETURN NULL; END IF;
    candidate := make_date(yy::integer, mm::integer, dd::integer);
    parts := regexp_split_to_array(v, '[-/]');
    IF parts[3]::integer = yy AND
       ((parts[1]::integer = dd AND parts[2]::integer = mm) OR
        (parts[1]::integer = mm AND parts[2]::integer = dd)) THEN RETURN candidate; END IF;
    RETURN NULL;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format OR numeric_value_out_of_range THEN
    RETURN NULL;
END $$;
"""


def derived_expressions(source, columns):
    """Devuelve nombre -> expresión; solo añade columnas con prefijo v_."""
    expressions = {}

    def add(name, expression):
        if name in columns or name in expressions:
            raise ValueError(f"Colisión de columna derivada: {name}")
        expressions[name] = expression

    def typed(column, kind):
        q = "r." + ident(column)
        expression = f"pg_temp.v_{kind}({q}::text)"
        if source == "edg" and kind == "date":
            suffix = column.removeprefix("fecha_")
            if all(f"{part}_{suffix}" in columns for part in ("anio", "mes", "dia")):
                expression = (f"pg_temp.v_edg_date({q}::text, r.{ident('anio_' + suffix)}::text, "
                              f"r.{ident('mes_' + suffix)}::text, r.{ident('dia_' + suffix)}::text)")
        add("v_" + column.lower(), expression)
        state = missing_state(q)
        add("v_" + column.lower() + "_estado",
            f"CASE WHEN ({state}) <> 'PRESENT' THEN ({state}) "
            f"WHEN {expression} IS NULL THEN 'INVALID_OR_UNRESOLVED' ELSE 'VALID' END")

    for column in columns:
        if column.startswith("fecha_"):
            typed(column, "date")

    numeric = ["edad", "cantidad", "dias_solucion"]
    if source == "enemdu":
        numeric = ["p03", "fexp", "ingpc", "ingrl"]
        typed("periodo", "period")
    for column in numeric:
        if column in columns:
            typed(column, "number")

    for column in columns:
        if column in {"sexo", "p02", "situacion_actual", "status", "autopsia", "mor_viol",
                      "pobreza", "epobreza", "empleo", "desempleo", "condact", "condactn",
                      "secemp", "rama1", "sector", "area", "area_hecho", "area_fall",
                      "tipo_arma", "arma", "clase_arma", "tipo_muerte", "tipo_lugar",
                      "etnia", "instruccion", "niv_inst", "p10a", "nacionalidad", "cod_edad",
                      "medida_edad", "genero", "motivacion", "motivo_desaparicion"}:
            q = "r." + ident(column)
            add("v_" + column, f"CASE WHEN {meaningful(q)} THEN {norm(q)} END")
            add("v_" + column + "_estado", missing_state(q))

    if source == "enemdu":
        province_code = "pg_temp.v_code(r.ciudad::text, 6)"
        canton_code = f"left({province_code}, 4)"
        add("v_codigo_ciudad", province_code)
        add("v_codigo_canton", canton_code)
        add("v_codigo_provincia", f"left({province_code}, 2)")
        add("v_provincia", "CASE WHEN dpa.variantes = 1 THEN dpa.provincia END")
        add("v_canton", "CASE WHEN dpa.variantes = 1 THEN dpa.canton END")
        add("v_dpa_estado", f"CASE WHEN {province_code} IS NULL THEN 'MISSING_OR_INVALID_CODE' "
            "WHEN dpa.codigo IS NULL THEN 'NOT_FOUND' WHEN dpa.variantes <> 1 THEN 'AMBIGUOUS' ELSE 'MATCHED' END")
    else:
        for column in columns:
            if column in {"provincia", "nombre_provincia", "prov_fall", "prov_insc", "prov_res", "provincia_localizacion"}:
                add("v_" + column, canonical_province("r." + ident(column)))
            elif column in {"canton", "nombre_canton", "cant_fall", "cant_insc"}:
                add("v_" + column, canonical_canton("r." + ident(column)))
            elif column in {"codigo_provincia", "codigo_canton", "codigo_parroquia"}:
                width = {"codigo_provincia": 2, "codigo_canton": 4, "codigo_parroquia": 6}[column]
                add("v_" + column, f"pg_temp.v_code(r.{ident(column)}::text, {width})")

    if "edad" in columns:
        unit = "v_cod_edad" if source == "edg" else "v_medida_edad" if source == "mdi_homicidio" else None
        condition = "TRUE" if unit is None else f"({expressions[unit]}) IN ('AÑOS', 'A')"
        add("v_edad_anios", f"CASE WHEN {condition} THEN pg_temp.v_number(r.edad::text) END")
    elif source == "enemdu":
        add("v_edad_anios", "pg_temp.v_number(r.p03::text)")

    if source == "edg":
        variants = [col for col in columns if col.lower().startswith(("numeracion", "numeración", "númeración"))]
        numeric_variants = [f"pg_temp.v_number(r.{ident(col)}::text)" for col in variants]
        if numeric_variants:
            add("v_numeracion", "COALESCE(" + ", ".join(numeric_variants + ["NULL::numeric"]) + ")")
            add("v_numeracion_conflicto", "(SELECT count(DISTINCT n) > 1 FROM unnest(ARRAY[" +
                ", ".join(numeric_variants) + "]) n)")

    # Coordenadas paralelas se mantienen separadas. No imputar ni intercambiar.
    pairs = [("latitud", "longitud"), ("latitud_desaparicion", "longitud_desaparicion"),
             ("latitud_localizacion", "longitud_localizacion"), ("coordenada_y", "coordenada_x")]
    for lat, lon in pairs:
        if lat in columns and lon in columns:
            for column in (lat, lon):
                typed(column, "number")

    return expressions


def dpa_join():
    province = canonical_province("nombre_provincia")
    canton = canonical_canton("nombre_canton")
    return f"""LEFT JOIN (
        SELECT pg_temp.v_code(codigo_canton::text, 4) codigo,
               count(DISTINCT ({province}, {canton})) variantes,
               min({province}) provincia, min({canton}) canton
        FROM catalogo.dpa_ecuador
        WHERE codigo_canton IS NOT NULL AND btrim(codigo_canton::text) <> ''
        GROUP BY pg_temp.v_code(codigo_canton::text, 4)
    ) dpa ON dpa.codigo = left(pg_temp.v_code(r.ciudad::text, 6), 4)"""
