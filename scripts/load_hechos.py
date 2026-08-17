import pandas as pd
import gc
from utils.config import engine
from utils.dwh_helpers import (
    rango_edad,
    get_dim,
    clear_dim_cache,
    merge_tiempo,
    merge_tiempo_multi,
    merge_dim,
    merge_geo,
    ensure_cols,
    save_fact,
)

# Columnas de dim_ubicacion usadas en los joins
UBICACION_JOIN_COLS = [
    "codigo_provincia", "provincia",
    "codigo_canton", "canton",
    "parroquia", "distrito", "circuito",
    "subcircuito", "zona", "area"
]


def load_fact_homicidio():
    print("Cargando fact_homicidio...")
    h = pd.read_sql("SELECT * FROM clean.homicidio_limpia", engine)

    h = merge_tiempo(h, "fecha_infraccion")

    h = merge_dim(
        h, "dim_ubicacion",
        join_cols=[
            "codigo_provincia", "provincia",
            "codigo_canton", "canton",
            "distrito", "circuito", "subcircuito", "zona"
        ],
    )

    h["edad"] = pd.to_numeric(h["edad"], errors="coerce")
    h["rango_edad"] = h["edad"].apply(rango_edad)

    h = merge_dim(
        h, "dim_persona",
        join_cols=[
            "sexo", "edad", "rango_edad", "etnia",
            "estado_civil", "nacionalidad", "instruccion"
        ],
    )

    h = merge_geo(h)

    h = merge_dim(
        h, "dim_arma",
        select_cols=["arma_key", "arma", "tipo_arma"],
        join_cols=["arma", "tipo_arma"],
    )

    h = merge_dim(
        h, "dim_motivacion",
        select_cols=["motivacion_key", "presunta_motivacion", "probable_causa_motivada"],
        join_cols=["presunta_motivacion", "probable_causa_motivada"],
    )

    fact = h[[
        "tiempo_key", "ubicacion_key", "persona_key", "geo_key",
        "arma_key", "motivacion_key", "tipo_muerte", "lugar",
        "tipo_lugar", "area_hecho"
    ]].copy()

    fact["conteo_homicidio"] = 1
    save_fact(fact, "fact_homicidio")


def load_fact_arma():
    print("Cargando fact_arma...")
    h = pd.read_sql("SELECT * FROM clean.mdi_arma_limpia", engine)

    h = merge_tiempo(h, "fecha_evento")

    h["provincia_join"] = h.get("nombre_provincia")
    h["canton_join"] = h.get("nombre_canton")
    h["parroquia_join"] = h.get("nombre_parroquia")
    h["distrito_join"] = h.get("nombre_distrito")
    h["circuito_join"] = h.get("nombre_circuito")
    h["subcircuito_join"] = h.get("nombre_subcircuito")
    h["area"] = h.get("area", None)

    h = merge_dim(
        h, "dim_ubicacion",
        left_cols=[
            "codigo_provincia", "provincia_join", "codigo_canton", "canton_join",
            "parroquia_join", "distrito_join", "circuito_join",
            "subcircuito_join", "zona", "area"
        ],
        join_cols=UBICACION_JOIN_COLS,
    )

    h = merge_geo(h)

    h = merge_dim(
        h, "dim_arma",
        select_cols=[
            "arma_key", "clase_arma", "calibre_estandarizado",
            "fabricacion", "nombre_objeto", "subtipo_objeto_robado"
        ],
        join_cols=[
            "clase_arma", "calibre_estandarizado", "fabricacion",
            "nombre_objeto", "subtipo_objeto_robado"
        ],
    )

    h = merge_dim(
        h, "dim_delito",
        select_cols=["delito_key", "delito", "tipo_delito", "modalidad", "codigo_iccs"],
        join_cols=["delito", "tipo_delito", "modalidad", "codigo_iccs"],
    )

    h["cantidad"] = pd.to_numeric(h.get("cantidad"), errors="coerce")

    cols_fact = [
        "tiempo_key", "ubicacion_key", "geo_key",
        "arma_key", "delito_key", "tipo_lugar", "cantidad"
    ]
    fact = ensure_cols(h, cols_fact)[cols_fact].copy()
    fact["conteo_evento"] = 1
    save_fact(fact, "fact_arma")


def load_fact_desaparicion():
    print("Cargando fact_desaparicion...")
    h = pd.read_sql("SELECT * FROM clean.mdi_desaparecido_limpia", engine)

    h = merge_tiempo_multi(h, {
        "fecha_desaparicion": "tiempo_desaparicion_key",
        "fecha_denuncia": "tiempo_denuncia_key",
        "fecha_conocimiento": "tiempo_conocimiento_key",
        "fecha_localizacion": "tiempo_localizacion_key",
    })

    h["parroquia_join"] = None
    h["area_join"] = h.get("area_hecho", h.get("area", None))

    if "subcircuito" not in h.columns:
        h["subcircuito"] = None
    if "zona" not in h.columns:
        h["zona"] = None

    h = merge_dim(
        h, "dim_ubicacion",
        left_cols=[
            "codigo_provincia", "provincia", "codigo_canton", "canton",
            "parroquia_join", "distrito", "circuito", "subcircuito",
            "zona", "area_join"
        ],
        join_cols=UBICACION_JOIN_COLS,
    )

    h["edad"] = pd.to_numeric(h.get("edad"), errors="coerce")
    if "rango_edad" not in h.columns:
        h["rango_edad"] = h["edad"].apply(rango_edad)

    h = merge_dim(
        h, "dim_persona",
        select_cols=["persona_key", "sexo", "edad", "rango_edad", "etnia", "nacionalidad"],
        join_cols=["sexo", "edad", "rango_edad", "etnia", "nacionalidad"],
    )

    h = merge_geo(h)

    h = merge_dim(
        h, "dim_motivacion",
        select_cols=[
            "motivacion_key", "motivacion", "motivacion_observada",
            "motivacion_desaparicion_observada", "motivo_desaparicion"
        ],
        join_cols=[
            "motivacion", "motivacion_observada",
            "motivacion_desaparicion_observada", "motivo_desaparicion"
        ],
    )

    h = merge_dim(
        h, "dim_estado_caso",
        select_cols=["estado_caso_key", "situacion_actual", "status"],
        join_cols=["situacion_actual", "status"],
    )

    h["dias_solucion"] = pd.to_numeric(h.get("dias_solucion"), errors="coerce")

    cols_fact = [
        "ubicacion_key", "persona_key", "geo_key",
        "motivacion_key", "estado_caso_key", "dias_solucion"
    ]
    for prefix in ["desaparicion", "denuncia", "conocimiento", "localizacion"]:
        cols_fact.append(f"tiempo_{prefix}_key")

    fact = ensure_cols(h, cols_fact)[cols_fact].copy()
    fact["conteo_desaparicion"] = 1
    save_fact(fact, "fact_desaparicion")


def load_fact_defuncion():
    print("Cargando fact_defuncion...")
    h = pd.read_sql("SELECT * FROM clean.edg_limpia", engine)

    h = merge_tiempo_multi(h, {
        "fecha_fall": "tiempo_fallecimiento_key",
        "fecha_insc": "tiempo_inscripcion_key",
        "fecha_nac": "tiempo_nacimiento_key",
    })

    h["codigo_provincia_join"] = None
    h["codigo_canton_join"] = None
    h["distrito_join"] = None
    h["circuito_join"] = None
    h["subcircuito_join"] = None
    h["zona_join"] = None

    h = merge_dim(
        h, "dim_ubicacion",
        left_cols=[
            "codigo_provincia_join", "prov_fall", "codigo_canton_join", "cant_fall",
            "parr_fall", "distrito_join", "circuito_join",
            "subcircuito_join", "zona_join", "area_fall"
        ],
        join_cols=UBICACION_JOIN_COLS,
    )

    h["edad"] = pd.to_numeric(h.get("edad"), errors="coerce")
    if "rango_edad" not in h.columns:
        h["rango_edad"] = h["edad"].apply(rango_edad)

    h = merge_dim(
        h, "dim_persona",
        select_cols=[
            "persona_key", "sexo", "edad", "rango_edad", "etnia",
            "estado_civil", "nacionalidad", "instruccion"
        ],
        left_cols=["sexo", "edad", "rango_edad", "etnia", "est_civil", "nac_fall", "niv_inst"],
        join_cols=["sexo", "edad", "rango_edad", "etnia", "estado_civil", "nacionalidad", "instruccion"],
    )

    cols_fact = [
        "tiempo_fallecimiento_key", "tiempo_inscripcion_key", "tiempo_nacimiento_key",
        "ubicacion_key", "persona_key",
        "causa", "causa103", "causa4", "causa67a", "causa67b", "causa80",
        "lugar_ocur", "lug_viol", "mor_viol", "autopsia"
    ]
    fact = ensure_cols(h, cols_fact)[cols_fact].copy()
    fact["conteo_defuncion"] = 1
    save_fact(fact, "fact_defuncion")


def load_fact_enemdu():
    print("Cargando fact_enemdu...")

    dim_tiempo = get_dim("dim_tiempo").copy()
    dim_ubicacion = get_dim("dim_ubicacion")
    dim_persona = get_dim("dim_persona")

    dim_tiempo["fecha"] = pd.to_datetime(dim_tiempo["fecha"])
    dt_dedup = dim_tiempo[["tiempo_key", "fecha"]].drop_duplicates(subset=["fecha"])

    dim_ubicacion_dedup = dim_ubicacion.drop_duplicates(subset=UBICACION_JOIN_COLS)
    dim_persona_dedup = dim_persona[
        ["persona_key", "sexo", "edad", "rango_edad", "estado_civil", "instruccion"]
    ].drop_duplicates(subset=["sexo", "edad", "rango_edad", "estado_civil", "instruccion"])

    chunk_size = 50000
    total_insertado = 0

    total_rows = pd.read_sql("SELECT COUNT(*) FROM clean.enemdu_limpia", engine).iloc[0, 0]
    print(f"Total de registros a procesar: {total_rows}")
    print(f"Iniciando procesamiento de fact_enemdu en chunks de {chunk_size} registros usando LIMIT/OFFSET...")

    for offset in range(0, total_rows, chunk_size):
        print(f"Leyendo desde offset {offset}...")
        query = f"SELECT * FROM clean.enemdu_limpia LIMIT {chunk_size} OFFSET {offset}"
        h = pd.read_sql(query, engine)

        if h.empty:
            break

        if "periodo" in h.columns:
            h["fecha_join"] = pd.to_datetime(h["periodo"].astype(str) + "01", format="%Y%m%d", errors="coerce")
            h = h.merge(dt_dedup, left_on="fecha_join", right_on="fecha", how="left")

        h["provincia_join"] = h.get("provincia", None)
        h["parroquia_join"] = None
        h["distrito_join"] = None
        h["circuito_join"] = None
        h["subcircuito_join"] = None

        if "zona" not in h.columns:
            h["zona"] = None
        if "area" not in h.columns:
            h["area"] = None

        if "prov" not in h.columns:
            if "ciudad" in h.columns:
                h["prov"] = h["ciudad"].astype(str).str.zfill(6).str[:2]
            else:
                h["prov"] = None

        h = h.merge(
            dim_ubicacion_dedup,
            left_on=[
                "prov", "provincia_join", "ciudad", "ciudad", "parroquia_join",
                "distrito_join", "circuito_join", "subcircuito_join", "zona", "area"
            ],
            right_on=UBICACION_JOIN_COLS,
            how="left"
        )

        h["edad_join"] = pd.to_numeric(h.get("p03"), errors="coerce")
        h["rango_edad_join"] = h["edad_join"].apply(rango_edad)

        h = h.merge(
            dim_persona_dedup,
            left_on=["p02", "edad_join", "rango_edad_join", "p06", "p10a"],
            right_on=["sexo", "edad", "rango_edad", "estado_civil", "instruccion"],
            how="left"
        )

        cols_fact = [
            "tiempo_key", "ubicacion_key", "persona_key", "id_vivienda",
            "id_hogar", "id_persona", "periodo", "fexp", "ingrl", "ingpc",
            "empleo", "desempleo", "subempleo", "sector", "pobreza", "pobreza_extrema"
        ]
        fact = ensure_cols(h, cols_fact)[cols_fact].copy()
        fact["conteo_persona"] = 1

        fact.to_sql("fact_enemdu", engine, schema="dwh", if_exists="append", index=False, chunksize=1000)
        total_insertado += len(fact)
        print(f"Insertados {total_insertado} / {total_rows} registros en fact_enemdu...")

        del h
        del fact
        gc.collect()

    print("fact_enemdu cargada completamente.")


def load_all_facts():
    """Carga todas las tablas de hechos cargando las dimensiones una sola vez."""
    print("Cargando todas las tablas de hechos...")

    for dim in [
        "dim_tiempo", "dim_ubicacion", "dim_persona", "dim_geo_punto",
        "dim_arma", "dim_motivacion", "dim_delito", "dim_estado_caso"
    ]:
        get_dim(dim)

    load_fact_homicidio()
    load_fact_arma()
    load_fact_desaparicion()
    load_fact_defuncion()
    load_fact_enemdu()

    clear_dim_cache()
    print("Todas las tablas de hechos cargadas.")