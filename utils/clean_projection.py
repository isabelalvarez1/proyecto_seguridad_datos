"""Contrato de publicación de datos validados a clean, sin reglas de DW.

No elimina observaciones. Los originales de campos transformados se conservan
en columnas *_original; las respuestas no numéricas no se convierten a cero.
"""
import re
from unidecode import unidecode

from utils.validation_sql import MISSING, ident, norm, sql_list


def column_mapping(raw_columns):
    """Nombres estables, sin perder columnas que colisionan al quitar tildes."""
    result = {}
    used = set()
    for original in raw_columns:
        base = re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", unidecode(original).strip().lower()))
        if not base:
            raise ValueError(f"Nombre de columna vacío: {original!r}")
        name = base
        suffix = 2
        while name in used:
            name = f"{base}__{suffix}"
            suffix += 1
        if len(name) > 63:
            raise ValueError(f"Nombre de columna demasiado largo: {name}")
        used.add(name)
        result[original] = name
    return result


def clean_text(expression):
    v = norm(expression)
    return f"CASE WHEN {expression} IS NULL OR {v} IN ({sql_list(MISSING)}) THEN NULL ELSE {v} END"


def coordinate_contract(lat, lon):
    a, b = 'r.' + ident('v_' + lat), 'r.' + ident('v_' + lon)
    valid = f"({a} BETWEEN -90 AND 90 AND {b} BETWEEN -180 AND 180 AND NOT ({a}=0 AND {b}=0))"
    state = (f"CASE WHEN {a}=0 AND {b}=0 THEN 'ZERO_PAIR' "
             f"WHEN {a} IS NULL OR {b} IS NULL THEN 'MISSING_OR_UNRESOLVED_PAIR' "
             f"WHEN NOT ({a} BETWEEN -90 AND 90 AND {b} BETWEEN -180 AND 180) THEN 'OUT_OF_RANGE' "
             "ELSE 'OBSERVED_NOT_IMPUTED' END")
    return f"CASE WHEN {valid} THEN {a} END", f"CASE WHEN {valid} THEN {b} END", state


def clean_projection(source, raw_info, available):
    mapping = column_mapping([item['column_name'] for item in raw_info])
    expressions = {}
    audit = []

    def add(name, expression):
        if name in expressions or len(name) > 63:
            raise ValueError(f"Columna de salida repetida o inválida: {name}")
        expressions[name] = expression

    for info in raw_info:
        original = info['column_name']
        name = mapping[original]
        raw = 'r.' + ident(original)
        derived = 'v_' + original.lower()
        if derived in available:
            expression = 'r.' + ident(derived)
        elif info['data_type'] in ('text', 'character varying', 'character'):
            # source_file es procedencia, no una categoría para homologar.
            expression = raw if name in {'source_file', 'source_sha256'} else clean_text(raw)
        else:
            expression = raw
        add(name, expression)
        # Todas las transformaciones de originales quedan reversibles.
        if expression != raw:
            add(name + '_original', raw)
        audit.append({'raw_column': original, 'clean_column': name,
                      'expression': expression, 'original_preserved': expression != raw})

    # Copiar estados y derivadas adicionales sin el prefijo de la fase de prueba.
    for derived in available:
        if not derived.startswith('v_'):
            continue
        name = derived[2:]
        if name not in expressions:
            add(name, 'r.' + ident(derived))

    if source == 'edg':
        # La primera variante también se preserva antes de la coalescencia.
        first = next((col for col, name in mapping.items() if name == 'numeracion'), None)
        if first is not None and 'numeracion_original' not in expressions:
            add('numeracion_original', 'r.' + ident(first))
        expressions['numeracion'] = 'r.v_numeracion'
        add('fecha_nac_posterior_fall', 'r.v_fecha_nac > r.v_fecha_fall')

    if source == 'enemdu':
        age = norm('r.p03')
        open_age = f"{age} IN ('98 Y MÁS', '98 Y MAS')"
        expressions['p03_estado'] = (
            f"CASE WHEN {open_age} THEN 'OPEN_ENDED_98_PLUS' "
            f"WHEN {age}='NO INFORMA' THEN 'UNKNOWN' ELSE r.v_p03_estado END")
        add('edad_censurada', f"COALESCE({open_age},FALSE)")
        add('edad_limite_inferior', f"CASE WHEN {open_age} THEN 98::numeric ELSE r.v_p03 END")
        income = norm('r.ingrl')
        expressions['ingrl_estado'] = (
            f"CASE WHEN {income}='NO INFORMA' THEN 'UNKNOWN' "
            f"WHEN {income}='GASTA MAS DE LO QUE GANA' THEN 'NON_NUMERIC_RESPONSE' ELSE r.v_ingrl_estado END")
        add('ingrl_respuesta', f"CASE WHEN r.v_ingrl IS NULL THEN {clean_text('r.ingrl')} END")
        add('anio', 'left(r.v_periodo,4)::integer')
        add('mes_periodo', 'right(r.v_periodo,2)::integer')
        # Se mantienen sector, secemp, rama1, condact y condactn separados.

    for lat, lon, label in (
        ('latitud', 'longitud', 'geo_estado'),
        ('latitud_desaparicion', 'longitud_desaparicion', 'geo_desaparicion_estado'),
        ('latitud_localizacion', 'longitud_localizacion', 'geo_localizacion_estado'),
        ('coordenada_y', 'coordenada_x', 'geo_estado'),
    ):
        if 'v_' + lat in available and 'v_' + lon in available:
            a, b, state = coordinate_contract(lat, lon)
            expressions[mapping[lat]] = a
            expressions[mapping[lon]] = b
            add(label, state)
            if source == 'mdi_homicidio':
                add('latitud', a)
                add('longitud', b)

    # Campos de auditoría conservados en toda la publicación.
    for name in ('_validation_run_id', '_raw_ctid', '_raw_hash'):
        add(name, 'r.' + ident(name))
    return expressions, audit
