"""EDA y limpieza conservadora aislada del DWH y del clean operativo.

Ejecutar desde la raíz: python -m analysis.run_clean_validation
No borra, refresca ni reemplaza tablas existentes. Todas las escrituras SQL
persistentes se limitan al esquema fijo clean_validacion, en tablas por ejecución.
"""

import argparse
import csv
from datetime import datetime, timezone
import importlib.metadata
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import traceback
import uuid

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy import text

from analysis.validation_rules import (
    MISSING, UNKNOWN, NOT_APPLICABLE, SOURCES, TARGET_SCHEMA, TEMP_FUNCTIONS,
    derived_expressions, dpa_join, ident, sql_list,
)
from utils.config import PROJECT_ROOT, engine


PROTECTED_SCHEMAS = ("raw", "clean", "dwh", "catalogo")
REPORT_ROOT = PROJECT_ROOT / "reports" / "eda"
RUN_PATTERN = re.compile(r"^[a-z0-9_]{1,25}$")


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def columns(conn, schema, table):
    return conn.execute(text("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema=:schema AND table_name=:table ORDER BY ordinal_position
    """), {"schema": schema, "table": table}).mappings().all()


def protected_snapshot(only_keys=None):
    """Control de contenido (no criptográfico), estructura y definición de vistas.

    Dos sumas de hashes de filas, conteos y columnas; incluyen multiplicidad.
    No exporta filas ni identificadores personales.
    """
    snapshot = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '20min'"))
            conn.execute(text("SET LOCAL jit = off"))
            relations = conn.execute(text("""
                SELECT n.nspname schema, c.relname name, c.relkind kind,
                       c.oid::bigint oid, c.relfilenode::bigint filenode
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname IN ('raw','clean','dwh','catalogo')
                  AND c.relkind IN ('r','p','m','v')
                ORDER BY n.nspname,c.relname
            """)).mappings().all()
            for relation in relations:
                schema, table = relation["schema"], relation["name"]
                if only_keys is not None and f"{schema}.{table}" not in only_keys:
                    continue
                qualified = f"{ident(schema)}.{ident(table)}"
                log(f"Control de conservación: {schema}.{table}")
                summary = dict(relation)
                summary["columns"] = [dict(item) for item in columns(conn, schema, table)]
                if relation["kind"] != "v":
                    row = conn.execute(text(f"""
                        SELECT count(*) rows,
                               COALESCE(sum(hashtextextended(r::text,0)::numeric),0)::text hash_sum_0,
                               COALESCE(sum(hashtextextended(r::text,1)::numeric),0)::text hash_sum_1
                        FROM {qualified} r
                    """)).mappings().one()
                    summary.update(dict(row))
                if relation["kind"] in ("v", "m"):
                    summary["definition"] = conn.execute(
                        text("SELECT pg_get_viewdef(:oid, true)"), {"oid": relation["oid"]}
                    ).scalar_one()
                snapshot[f"{schema}.{table}"] = summary
    return snapshot


def profile(conn, schema, table, column_info, total):
    """Perfil completo; desconocido/no aplicable se reportan por separado."""
    expressions = []
    for info in column_info:
        q = ident(info["column_name"])
        # Conserva las diferencias de clasificación sin usar códigos numéricos
        # como 0/9/99/999: requieren diccionarios, no son nulos universales.
        v = f"upper(btrim({q}::text, E' \\t\\r\\n'))"
        expressions.extend([
            f"count(*)-count({q})",
            f"count(*) FILTER (WHERE {v} IN ({sql_list(MISSING)}))",
            f"count(*) FILTER (WHERE {v} IN ({sql_list(UNKNOWN)}))",
            f"count(*) FILTER (WHERE {v} IN ({sql_list(NOT_APPLICABLE)}))",
        ])
    values = conn.execute(text(f"SELECT {', '.join(expressions)} FROM {ident(schema)}.{ident(table)}")).one()
    rows = []
    for i, info in enumerate(column_info):
        null, sentinel, unknown, na = values[i * 4:i * 4 + 4]
        rows.append({
            "variable": info["column_name"], "tipo_sql": info["data_type"], "registros": total,
            "null_sql": null, "vacio_o_marcador": sentinel, "desconocido": unknown,
            "no_aplicable": na, "presente_no_clasificado_como_faltante": total - null - sentinel - unknown - na,
            "pct_ausente_sin_desconocidos": round((null + sentinel) * 100 / max(total, 1), 4),
            "pct_ausente_o_desconocido": round((null + sentinel + unknown) * 100 / max(total, 1), 4),
        })
    return rows


def candidate_checks(source, available):
    checks = {}
    if "v_edad_anios" in available:
        checks["edad_anios_fuera_0_120_revisar"] = "v_edad_anios < 0 OR v_edad_anios > 120"
    if source == "mdi_arma":
        checks["cantidad_negativa"] = "v_cantidad < 0"
        checks["cantidad_cero_revisar"] = "v_cantidad = 0"
        checks["cantidad_no_entera_revisar"] = "v_cantidad <> trunc(v_cantidad)"
    if source == "enemdu":
        checks["factor_no_positivo"] = "v_fexp <= 0"
        checks["ingpc_negativo_revisar"] = "v_ingpc < 0"
        checks["ingrl_negativo_revisar"] = "v_ingrl < 0"
        checks["dpa_ambiguo"] = "v_dpa_estado = 'AMBIGUOUS'"
        checks["dpa_sin_correspondencia"] = "v_dpa_estado = 'NOT_FOUND'"
    for date in ("v_fecha_fall", "v_fecha_infraccion", "v_fecha_evento", "v_fecha_desaparicion", "v_fecha_denuncia"):
        if date in available:
            checks[date + "_futura"] = f"{ident(date)} > CURRENT_DATE"
    if source == "edg":
        checks["nacimiento_posterior_fallecimiento"] = "v_fecha_nac > v_fecha_fall"
        checks["numeracion_en_conflicto"] = "v_numeracion_conflicto"
    if source == "mdi_desaparecido":
        checks["denuncia_anterior_desaparicion_revisar"] = "v_fecha_denuncia < v_fecha_desaparicion"
        checks["localizacion_anterior_desaparicion"] = "v_fecha_localizacion < v_fecha_desaparicion"
        checks["dias_solucion_negativos"] = "v_dias_solucion < 0"
        checks["dias_no_coinciden_calendario_revisar"] = (
            "v_dias_solucion <> v_fecha_localizacion - v_fecha_desaparicion")
    for lat, lon in (("latitud", "longitud"), ("latitud_desaparicion", "longitud_desaparicion"),
                     ("latitud_localizacion", "longitud_localizacion"), ("coordenada_y", "coordenada_x")):
        if "v_" + lat in available and "v_" + lon in available:
            a, b = ident("v_" + lat), ident("v_" + lon)
            checks[lat + "_fuera_rango_global"] = f"{a} NOT BETWEEN -90 AND 90"
            checks[lon + "_fuera_rango_global"] = f"{b} NOT BETWEEN -180 AND 180"
            checks[lat + "_par_cero"] = f"{a}=0 AND {b}=0"
            # Solo señal de revisión, no regla de eliminación; incluye Galápagos.
            checks[lat + "_fuera_envolvente_ecuador_revisar"] = (
                f"{a} NOT BETWEEN -6 AND 2 OR {b} NOT BETWEEN -93 AND -74")
    return checks


def coverage(conn, target, source):
    date = {"mdi_homicidio": "v_fecha_infraccion", "mdi_arma": "v_fecha_evento",
            "mdi_desaparecido": "v_fecha_desaparicion", "edg": "v_fecha_fall"}.get(source)
    year = "left(v_periodo,4)::integer" if source == "enemdu" else f"extract(year from {ident(date)})::integer"
    month = "right(v_periodo,2)::integer" if source == "enemdu" else f"extract(month from {ident(date)})::integer"
    return [dict(row) for row in conn.execute(text(f"""
        SELECT {year} anio, {month} mes, count(*) registros
        FROM {target} GROUP BY 1,2 ORDER BY 1 NULLS LAST,2 NULLS LAST
    """)).mappings()]


def numeric_summaries(conn, target, derived):
    numeric = [name for name in derived if name in {
        "v_edad_anios", "v_edad", "v_p03", "v_cantidad", "v_dias_solucion", "v_fexp", "v_ingpc", "v_ingrl"}]
    rows = []
    for name in numeric:
        q = ident(name)
        result = conn.execute(text(f"""
            SELECT count({q}) validos, min({q}) minimo, max({q}) maximo,
                   avg({q}) media,
                   percentile_cont(ARRAY[0.01,0.25,0.5,0.75,0.99])
                       WITHIN GROUP (ORDER BY {q}) percentiles
            FROM {target}
        """)).mappings().one()
        p = result["percentiles"] or [None] * 5
        rows.append({"variable": name, **{key: result[key] for key in ("validos", "minimo", "maximo", "media")},
                     **dict(zip(("p01", "p25", "mediana", "p75", "p99"), p))})
    return rows


def numeric_histograms(conn, target, directory, summaries):
    """Histogramas agregados: centro p01-p99, colas y nulos contabilizados."""
    output = []
    for summary in summaries:
        name = summary['variable']
        low, high = summary['p01'], summary['p99']
        if low is None or high is None or not math.isfinite(float(low)) or not math.isfinite(float(high)):
            continue
        if float(low) == float(high):
            counts = conn.execute(text(f"""
                SELECT CASE WHEN {ident(name)} IS NULL THEN 'NULL'
                            WHEN {ident(name)} = CAST(:value AS numeric) THEN 'CENTRO_CONSTANTE'
                            ELSE 'FUERA_CENTRO_CONSTANTE' END intervalo, count(*) registros
                FROM {target} GROUP BY 1
            """), {'value': str(low)}).mappings()
            output.extend({'variable': name, **dict(row), 'limite_inferior': low, 'limite_superior': high}
                          for row in counts)
            continue
        q = ident(name)
        rows = conn.execute(text(f"""
            SELECT width_bucket({q}, CAST(:low AS numeric), CAST(:high AS numeric), 25) bucket,
                   count(*) registros
            FROM {target} GROUP BY 1 ORDER BY 1 NULLS LAST
        """), {'low': str(low), 'high': str(high)}).mappings().all()
        central = []
        below = above = missing = 0
        for row in rows:
            bucket = row['bucket']
            label = 'NULL' if bucket is None else 'MENOR_P01' if bucket == 0 else 'MAYOR_O_IGUAL_P99' if bucket == 26 else str(bucket)
            output.append({'variable': name, 'intervalo': label, 'registros': row['registros'],
                           'limite_inferior': low, 'limite_superior': high})
            if bucket is None:
                missing += row['registros']
            elif bucket == 0:
                below += row['registros']
            elif bucket == 26:
                above += row['registros']
            else:
                central.append(row)
        fig, ax = plt.subplots(figsize=(9, 4))
        width = (float(high) - float(low)) / 25
        ax.bar([float(low) + (row['bucket'] - 1) * width for row in central],
               [row['registros'] for row in central], width=width, align='edge', color='#2372a8')
        ax.set(xlabel=f'{name} (códigos especiales pendientes de diccionario)', ylabel='Registros',
               title=f'Centro p01-p99; cola inferior={below}, superior={above}, nulos={missing}')
        fig.tight_layout()
        fig.savefig(directory / f'histograma_{name}.png', dpi=180)
        plt.close(fig)
    write_csv(directory / 'histogramas_numericos.csv', output)


def frequencies(conn, target, derived):
    fields = [name for name in derived if name.endswith("_estado") or name in {
        "v_sexo", "v_p02", "v_tipo_arma", "v_arma", "v_clase_arma", "v_tipo_muerte",
        "v_situacion_actual", "v_status", "v_autopsia", "v_mor_viol", "v_cod_edad",
        "v_pobreza", "v_epobreza", "v_condact", "v_condactn", "v_secemp", "v_rama1", "v_sector"}]
    rows = []
    for field in fields:
        results = conn.execute(text(f"""
            SELECT {ident(field)}::text categoria, count(*) registros
            FROM {target} GROUP BY 1 ORDER BY 2 DESC,1 NULLS FIRST LIMIT 15
        """)).mappings()
        rows.extend({"variable": field, **dict(row)} for row in results)
    return rows


def per_file_profile(conn, target, derived, original_columns):
    if "source_file" not in original_columns:
        return {"disponible": False, "motivo": "raw no conserva source_file; no inferir año ni archivo."}
    fields = [name for name in derived if name.endswith("_estado")]
    expressions = []
    for field in fields:
        expressions.append(f"count(*) FILTER (WHERE {ident(field)}='VALID' OR {ident(field)}='PRESENT') AS {ident(field)}")
    extra = ", " + ", ".join(expressions) if expressions else ""
    results = conn.execute(text(f"SELECT source_file,count(*) registros {extra} FROM {target} GROUP BY 1 ORDER BY 1")).mappings()
    return {"disponible": True, "conteos_validos_o_presentes": [dict(row) for row in results]}


def logical_duplicate_summary(conn, target, source):
    keys = {
        "mdi_homicidio": ["v_fecha_infraccion", "codigo_canton", "sexo", "edad", "arma"],
        "mdi_arma": ["v_fecha_evento", "codigo_canton", "nombre_objeto", "clase_arma"],
        "mdi_desaparecido": ["v_fecha_desaparicion", "codigo_canton", "sexo", "edad"],
        "edg": ["source_file", "v_numeracion"],
        "enemdu": ["v_periodo", "id_persona"],
    }[source]
    key_list = ", ".join(ident(key) for key in keys)
    present = " AND ".join(f"{ident(key)} IS NOT NULL AND btrim({ident(key)}::text) <> ''" for key in keys)
    result = conn.execute(text(f"""
        SELECT count(*) grupos_repetidos, COALESCE(sum(n-1),0) filas_adicionales,
               COALESCE(sum(n),0) filas_en_grupos
        FROM (SELECT count(*) n FROM {target} WHERE {present}
              GROUP BY {key_list} HAVING count(*)>1) g
    """)).mappings().one()
    return {"clave_candidata": keys, "no_es_prueba_de_duplicado": True, **dict(result)}


def process_source(source, run_id, report_dir, baseline):
    table = f"{source}_{run_id}"
    if source not in SOURCES or not RUN_PATTERN.fullmatch(run_id) or len(table) > 63:
        raise ValueError("Destino de validación no permitido")
    target = f"{ident(TARGET_SCHEMA)}.{ident(table)}"
    directory = report_dir / source
    directory.mkdir(exist_ok=True)
    log(f"Iniciando {source} -> {TARGET_SCHEMA}.{table}")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL statement_timeout = '20min'"))
            conn.execute(text("SET LOCAL jit = off"))
            conn.execute(text("SET LOCAL work_mem = '64MB'"))
            conn.execute(text(TEMP_FUNCTIONS))
            info = columns(conn, "raw", source)
            raw_columns = [item["column_name"] for item in info]
            if any(name.startswith(("v_", "_validation_", "_raw_")) for name in raw_columns):
                raise ValueError("Prefijo de validación ya presente en raw")
            derived = derived_expressions(source, raw_columns)
            total = baseline[f"raw.{source}"]["rows"]
            log(f"{source}: perfil de las {len(info)} variables originales")
            if (directory / "perfil_raw.csv").exists():
                with (directory / "perfil_raw.csv").open(encoding="utf-8-sig", newline="") as f:
                    raw_profile = list(csv.DictReader(f))
                for item in raw_profile:
                    item["pct_ausente_o_desconocido"] = float(item["pct_ausente_o_desconocido"])
                log(f"{source}: reutilizando perfil original de esta ejecución")
            else:
                raw_profile = profile(conn, "raw", source, info, total)
                write_csv(directory / "perfil_raw.csv", raw_profile)
            log(f"{source}: construyendo tabla aislada, conservando todos los originales")
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ident(TARGET_SCHEMA)}"))
            create_validation_table(conn, target, source, run_id, raw_columns, derived)
            output_count = conn.execute(text(f"SELECT count(*) FROM {target}")).scalar_one()
            if output_count != total:
                raise AssertionError(f"Filas alteradas: {total} -> {output_count}")
            # Comprobar que CTAS conservó valores originales, no solo las filas.
            original_record = "ROW(" + ", ".join(ident(col) for col in raw_columns) + ")::text"
            mismatches = conn.execute(text(f"SELECT count(*) FROM {target} WHERE md5({original_record}) <> _raw_hash")).scalar_one()
            if mismatches:
                raise AssertionError(f"Se alteraron originales: {mismatches}")
            log(f"{source}: {output_count:,} filas conservadas; evaluando calidad y distribuciones")
            new_info = [item for item in columns(conn, TARGET_SCHEMA, table) if item["column_name"] in derived]
            write_csv(directory / "perfil_derivadas.csv", profile(conn, TARGET_SCHEMA, table, new_info, output_count))
            numeric = numeric_summaries(conn, target, derived)
            write_csv(directory / "distribuciones_numericas.csv", numeric)
            numeric_histograms(conn, target, directory, numeric)
            cats = frequencies(conn, target, derived)
            write_csv(directory / "frecuencias_derivadas.csv", cats)
            monthly = coverage(conn, target, source)
            write_csv(directory / "cobertura_mensual.csv", monthly)
            file_profile = per_file_profile(conn, target, derived, raw_columns)
            write_json(directory / "cobertura_por_archivo.json", file_profile)
            checks = candidate_checks(source, derived)
            expressions = [f"count(*) FILTER (WHERE ({condition})) AS {ident(name)}" for name, condition in checks.items()]
            quality = dict(conn.execute(text(f"SELECT {', '.join(expressions)} FROM {target}")).mappings().one()) if checks else {}
            duplicates = dict(conn.execute(text(f"""
                SELECT count(*) grupos_hash_repetidos, COALESCE(sum(n-1),0) filas_adicionales,
                       COALESCE(sum(n),0) filas_en_grupos
                FROM (SELECT count(*) n FROM {target} GROUP BY _raw_hash HAVING count(*)>1) d
            """)).mappings().one())
            logical = logical_duplicate_summary(conn, target, source)
            comparison = operational_comparison(conn, source)
            summary = {
                "source": f"raw.{source}", "target": f"{TARGET_SCHEMA}.{table}",
                "rows_input": total, "rows_output": output_count, "rows_deleted": 0,
                "original_value_mismatches": mismatches,
                "raw_columns": [dict(item) for item in info],
                "derived_expressions": derived, "checks": quality,
                "duplicate_candidates_original_row_including_source_file_md5": duplicates,
                "logical_duplicate_candidates": logical,
                "operational_clean_read_only_comparison": comparison,
                "coverage": monthly, "numeric_summaries": numeric,
                "status_counts": [row for row in cats if row["variable"].endswith("_estado")],
                "file_coverage": file_profile,
            }
            write_json(directory / "resumen.json", summary)
    make_plots(directory, source, raw_profile, monthly, cats)
    log(f"{source}: tabla confirmada y reportes guardados")
    return summary


def sql_string(value):
    return "'" + value.replace("'", "''") + "'"


def validation_select(source, run_id, raw_columns, derived, predicate="TRUE"):
    """Materializar por bloque evita recalcular regex/parseos en cada estado."""
    from analysis.validation_rules import norm
    normalized = {}
    rewritten = dict(derived)
    for i, column in enumerate(raw_columns):
        expression = norm("r." + ident(column))
        if any(expression in value for value in rewritten.values()):
            name = f"_validation_norm_{i}"
            normalized[name] = expression
            rewritten = {key: value.replace(expression, "r." + ident(name)) for key, value in rewritten.items()}
    # Las funciones temporales no anidan llamadas entre sus argumentos.
    functions = {}
    join = dpa_join() if source == "enemdu" else ""
    pattern = re.compile(r"pg_temp\.v_\w+\([^()]+\)")
    for expression in list(rewritten.values()) + [join]:
        for call in pattern.findall(expression):
            # El DPA interno solo tiene 230 filas; se optimizan llamadas a r.
            if "r." in call and call not in functions:
                functions[call] = f"_validation_parsed_{len(functions)}"
    for call, name in functions.items():
        rewritten = {key: value.replace(call, "r." + ident(name)) for key, value in rewritten.items()}
        join = join.replace(call, "r." + ident(name))
    norm_list = ", " + ", ".join(expr + " AS " + ident(name) for name, expr in normalized.items()) if normalized else ""
    parsed_list = ", " + ", ".join(expr + " AS " + ident(name) for expr, name in functions.items()) if functions else ""
    original_list = ", ".join("r." + ident(column) for column in raw_columns)
    extras = ", ".join(expr + " AS " + ident(name) for name, expr in rewritten.items())
    return f"""
        WITH normalized AS MATERIALIZED (
            SELECT r.*, r.ctid::text AS _raw_ctid, md5(r::text) AS _raw_hash {norm_list}
            FROM raw.{ident(source)} r WHERE {predicate}
        ), parsed AS MATERIALIZED (SELECT r.* {parsed_list} FROM normalized r)
        SELECT {original_list}, {sql_string(run_id)}::text AS _validation_run_id,
               r._raw_ctid, r._raw_hash, {extras}
        FROM parsed r {join}
    """


def create_validation_table(conn, target, source, run_id, raw_columns, derived):
    if source != "enemdu":
        conn.execute(text(f"CREATE TABLE {target} AS " + validation_select(source, run_id, raw_columns, derived)))
        return
    # CTID range scans evitan LIMIT/OFFSET y mantienen una sola instantánea
    # REPEATABLE READ. Solo se usan tablas raw ordinarias, no particionadas.
    kind = conn.execute(text("SELECT relkind FROM pg_class WHERE oid=to_regclass(:t)"),
                        {"t": "raw." + source}).scalar_one()
    if kind != "r":
        raise ValueError("El procesado por páginas requiere tabla raw ordinaria")
    pages = conn.execute(text("SELECT ceil(pg_relation_size(to_regclass(:t))::numeric / current_setting('block_size')::integer)::bigint"),
                         {"t": "raw." + source}).scalar_one()
    conn.execute(text(f"CREATE TABLE {target} AS " + validation_select(source, run_id, raw_columns, derived, "FALSE")))
    page_step = 4000
    for first in range(0, pages, page_step):
        last = min(first + page_step, pages)
        predicate = f"r.ctid >= '({first},0)'::tid AND r.ctid < '({last},0)'::tid"
        result = conn.execute(text(f"INSERT INTO {target} " + validation_select(source, run_id, raw_columns, derived, predicate)))
        log(f"ENEMDU páginas {first}-{last}/{pages}: {result.rowcount:,} filas")


def operational_comparison(conn, source):
    table = SOURCES[source]
    info = columns(conn, "clean", table)
    if not info:
        # La instalación local puede conservar las salidas anteriores con _1.
        candidate = table + "_1"
        info = columns(conn, "clean", candidate)
        if not info:
            return {"available": False, "expected_tables": [table, candidate]}
        table = candidate
    qualified = f"clean.{ident(table)}"
    result = {"available": True, "table": f"clean.{table}",
              "rows": conn.execute(text(f"SELECT count(*) FROM {qualified}")).scalar_one()}
    if source == "enemdu":
        result["periodo_sin_dato_o_null"] = conn.execute(text(
            f"SELECT count(*) FROM {qualified} WHERE periodo IS NULL OR periodo='SIN_DATO'"
        )).scalar_one()
    elif source == "edg":
        result["fecha_fall_null"] = conn.execute(text(f"SELECT count(*) FROM {qualified} WHERE fecha_fall IS NULL")).scalar_one()
    return result


def make_plots(directory, source, raw_profile, monthly, cats):
    largest = sorted(raw_profile, key=lambda row: row["pct_ausente_o_desconocido"], reverse=True)[:20]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh([row["variable"] for row in largest][::-1],
            [row["pct_ausente_o_desconocido"] for row in largest][::-1], color="#2372a8")
    ax.set(xlabel="Ausencia o respuesta desconocida (%)", xlim=(0, 100), title=f"{source}: 20 variables con mayor ausencia")
    fig.tight_layout()
    fig.savefig(directory / "ausencia_variables.png", dpi=180)
    plt.close(fig)
    years = {}
    for row in monthly:
        if row["anio"] is not None:
            years[row["anio"]] = years.get(row["anio"], 0) + row["registros"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([str(year) for year in sorted(years)], [years[year] for year in sorted(years)], color="#2372a8")
    ax.set(xlabel="Año interpretado (no garantiza cobertura completa)", ylabel="Registros", title=f"{source}: cobertura recuperable")
    ax.tick_params(axis="x", labelrotation=60)
    fig.tight_layout()
    fig.savefig(directory / "cobertura_anual.png", dpi=180)
    plt.close(fig)
    for field in ("v_sexo", "v_p02", "v_situacion_actual", "v_autopsia", "v_pobreza"):
        values = [row for row in cats if row["variable"] == field]
        if not values:
            continue
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.barh([str(row["categoria"] or "AUSENTE/DESCONOCIDO") for row in values][::-1],
                [row["registros"] for row in values][::-1], color="#2372a8")
        ax.set(xlabel="Registros", title=f"{source}: {field}")
        fig.tight_layout()
        fig.savefig(directory / f"{field}.png", dpi=180)
        plt.close(fig)


def crossing_coverage(summaries):
    """Solo cobertura agregada; no modifica ni construye un DW."""
    results = {}
    with engine.connect() as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))
        for source, summary in summaries.items():
            target = summary["target"]
            # Los destinos fueron generados y validados por process_source.
            date = {"mdi_homicidio": "v_fecha_infraccion", "mdi_arma": "v_fecha_evento",
                    "mdi_desaparecido": "v_fecha_desaparicion", "edg": "v_fecha_fall"}.get(source)
            year = "left(v_periodo,4)::integer" if source == "enemdu" else f"extract(year from {date})::integer"
            province = {"mdi_homicidio": "v_provincia", "mdi_arma": "v_nombre_provincia",
                        "mdi_desaparecido": "v_provincia", "edg": "v_prov_fall", "enemdu": "v_provincia"}[source]
            rows = conn.execute(text(f"""
                SELECT {year} anio, {province} provincia, count(*) registros
                FROM {target} GROUP BY 1,2 ORDER BY 1 NULLS LAST,2 NULLS LAST
            """)).mappings().all()
            results[source] = [dict(row) for row in rows]
    return results


def write_findings(report_dir, summaries, checks):
    lines = ["# Limpieza de validación y EDA", "", f"Ejecución: `{report_dir.name}`.", "",
             "## Alcance", "", "Se conservaron los originales y todas las filas. Las variables `v_` son derivadas conservadoras;",
             "los estados distinguen ausencia, desconocido, no aplicable y conversión no resuelta.",
             "No se imputaron valores, no se eliminaron duplicados y no se actualizaron clean ni el DW.", "",
             "## Conservación de esquemas protegidos", "", f"Comparación antes/después: **{checks['status']}**.", "",
             "Se compararon estructura, conteos, dos sumas de hashes y definiciones de vistas.",
             "Los hashes son controles no criptográficos; el SQL de escritura solo tiene destino clean_validacion.", "",
             "## Tablas generadas", "", "| Fuente | Salida | Filas | Eliminadas |", "|---|---|---:|---:|"]
    for source, item in summaries.items():
        lines.append(f"| {source} | `{item['target']}` | {item['rows_output']} | 0 |")
    for source, item in summaries.items():
        lines.extend(["", f"## {source}", "", "### Estados de campos derivados", ""])
        for row in item["status_counts"]:
            lines.append(f"- `{row['variable']}` / {row['categoria']}: {row['registros']}.")
        lines.extend(["", "### Señales de revisión (no implican eliminación)", ""])
        for check, count in item["checks"].items():
            lines.append(f"- {check}: {count}.")
        lines.extend(["", f"Candidatos de duplicación exacta por hash (incluye source_file): `{item['duplicate_candidates_original_row_including_source_file_md5']}`.",
                      f"Clave lógica exploratoria, no prueba de duplicado: `{item['logical_duplicate_candidates']}`.",
                      f"Comparación con clean actual: `{item['operational_clean_read_only_comparison']}`."])
    lines.extend(["", "## Límites e interpretación", "",
                  "- Fechas ambiguas con año al final quedan pendientes salvo EDG cuando día, mes y año originales confirman la interpretación.",
                  "- Las abreviaturas de mes con dos dígitos de año se interpretan como 20xx para estas fuentes; no se infieren períodos ausentes.",
                  "- Una conversión de fecha válida no demuestra que la fecha sea históricamente correcta.",
                  "- Se conservan códigos de autopsia, educación, sexo y empleo sin inventar equivalencias.",
                  "- La edad en días/meses/horas no se convierte a años; v_edad_anios exige unidad en años cuando existe.",
                  "- Las coordenadas no se imputan ni se intercambian; la envolvente de Ecuador es solo un control aproximado.",
                  "- Los códigos DPA con más de una correspondencia se marcan ambiguos y no reciben nombres arbitrarios.",
                  "- Los percentiles y medias de ingresos aún pueden incluir códigos especiales no documentados; no son estimaciones oficiales.",
                  "- No se calculan tasas poblacionales o de encuesta: faltan diccionarios, universos y diseño muestral.",
                  "- La cobertura conjunta solo identifica pares posibles; no demuestra comparabilidad ni vinculación de personas.",
                  "- Para aprobar clean se necesita revisar señales, diccionarios y casos por referencia dentro de PostgreSQL.", ""])
    (report_dir / "hallazgos.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", choices=list(SOURCES), default=list(SOURCES))
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4])
    parser.add_argument("--plan", action="store_true", help="Mostrar destinos sin conectar ni escribir")
    parser.add_argument("--resume", action="store_true", help="Reanudar una ejecución fallida sin repetir fuentes confirmadas")
    args = parser.parse_args()
    if not RUN_PATTERN.fullmatch(args.run_id):
        parser.error("run-id: 1 a 25 caracteres, letras minúsculas, números o guion bajo")
    sources = list(dict.fromkeys(args.sources))
    if args.plan:
        for source in sources:
            print(f"raw.{source} -> {TARGET_SCHEMA}.{source}_{args.run_id}")
        return
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report_dir = REPORT_ROOT / args.run_id
    if args.resume:
        manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["status"] != "FAILED" or manifest["sources"] != sources:
            raise ValueError("Solo se reanuda una ejecución fallida con las mismas fuentes")
        write_json(report_dir / ("manifest_failed_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"), manifest)
        manifest["status"] = "RUNNING"
        manifest["pid"] = os.getpid()
        manifest.pop("error", None)
    else:
        report_dir.mkdir(exist_ok=False)
        manifest = {"run_id": args.run_id, "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "RUNNING", "pid": os.getpid(), "sources": sources,
                "target_schema": TARGET_SCHEMA, "protected_schemas": PROTECTED_SCHEMAS,
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip(),
                "working_tree_status": subprocess.check_output(["git", "status", "--short"], cwd=PROJECT_ROOT, text=True),
                "versions": {package: importlib.metadata.version(package) for package in
                             ("pandas", "numpy", "SQLAlchemy", "psycopg2-binary", "matplotlib")}}
    manifest.setdefault("code_revisions", []).append({
        "time": datetime.now(timezone.utc).isoformat(), "resume": args.resume,
        "sha256": {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
                   for name in ["analysis/run_clean_validation.py", "analysis/validation_rules.py"]}})
    write_json(report_dir / "manifest.json", manifest)
    summaries = {}
    before = None
    try:
        log(f"Ejecución {args.run_id}; reportes: {report_dir}")
        if args.resume:
            before = json.loads((report_dir / "protected_before.json").read_text(encoding="utf-8"))
        else:
            before = protected_snapshot()
            write_json(report_dir / "protected_before.json", before)
        for source in sources:
            if source in manifest.get("completed_sources", {}):
                summaries[source] = json.loads((report_dir / source / "resumen.json").read_text(encoding="utf-8"))
                log(f"Conservando fuente ya confirmada: {source}")
                continue
            summaries[source] = process_source(source, args.run_id, report_dir, before)
            manifest["completed_sources"] = {name: item["target"] for name, item in summaries.items()}
            write_json(report_dir / "manifest.json", manifest)
        crossings = crossing_coverage(summaries)
        write_json(report_dir / "cobertura_provincia_anio.json", crossings)
        pairs = {name: {(row["anio"], row["provincia"]) for row in rows
                        if row["anio"] is not None and row["provincia"] is not None}
                 for name, rows in crossings.items()}
        shared = [{"fuente_a": a, "fuente_b": b, "pares_compartidos": len(pairs[a] & pairs[b])}
                  for a in pairs for b in pairs if a < b]
        write_csv(report_dir / "cruces_candidatos.csv", shared)
        log("Comprobando conservación de raw, clean, dwh y catálogo")
        after = protected_snapshot()
        write_json(report_dir / "protected_after.json", after)
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        conservation = {"status": "UNCHANGED" if not changed else "CHANGED_REQUIRES_REVIEW", "changed_objects": changed}
        write_json(report_dir / "conservacion.json", conservation)
        write_findings(report_dir, summaries, conservation)
        if changed:
            raise AssertionError(f"Cambios detectados en objetos protegidos: {changed}")
        manifest["status"] = "COMPLETED"
        log("Finalizado: originales conservados, clean y DW sin cambios")
    except BaseException as error:
        manifest["status"] = "FAILED"
        manifest["error"] = str(error)
        (report_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(report_dir / "manifest.json", manifest)


if __name__ == "__main__":
    main()
