import pandas as pd
import gc
from utils.config import engine
from utils.dwh_helpers import (
    rango_edad,
    normalizar_texto as clean_txt,
    fill_dim_text,
    dpa_from_codigos,
    MESES_ES,
)
from utils.cleaning import normalize_geo_frame


READ_CHUNKSIZE = 50_000
WRITE_CHUNKSIZE = 500


def read_clean_chunks(table, columns=None):
    query = f"SELECT {', '.join(columns) if columns else '*'} FROM clean.{table}"
    return pd.read_sql(query, engine, chunksize=READ_CHUNKSIZE)


def append_dwh(df, table):
    if df.empty:
        return

    df.to_sql(
        table,
        engine,
        schema="dwh",
        if_exists="append",
        index=False,
        chunksize=WRITE_CHUNKSIZE
    )


def remove_existing(df, table, cols):
    existentes = pd.read_sql(
        f"SELECT {', '.join(cols)} FROM dwh.{table}",
        engine
    )

    if existentes.empty:
        return df.drop_duplicates()

    df = clean_txt(df.copy())
    existentes = clean_txt(existentes.copy())

    merged = df.merge(
        existentes.drop_duplicates(),
        on=cols,
        how="left",
        indicator=True
    )

    nuevos = merged[merged["_merge"] == "left_only"][cols]
    return nuevos.drop_duplicates()


def load_dim_tiempo():
    print("Cargando dim_tiempo...")

    tablas_fechas = {
        "homicidio_limpia": ["fecha_infraccion"],
        "mdi_arma_limpia": ["fecha_evento"],
        "mdi_desaparecido_limpia": [
            "fecha_desaparicion",
            "fecha_denuncia",
            "fecha_conocimiento",
            "fecha_localizacion"
        ],
        "edg_limpia": ["fecha_fall", "fecha_insc", "fecha_nac"],
    }

    fechas_acumuladas = []

    for tabla, columnas in tablas_fechas.items():
        print(f"  Leyendo {tabla}...")

        for chunk in read_clean_chunks(tabla, columnas):
            for col in columnas:
                if col in chunk.columns:
                    tmp = pd.DataFrame()
                    tmp["fecha"] = pd.to_datetime(chunk[col], errors="coerce")
                    tmp = tmp.dropna()
                    fechas_acumuladas.append(tmp)

            del chunk
            gc.collect()

    print("  Leyendo enemdu_limpia...")

    for chunk in read_clean_chunks("enemdu_limpia", ["periodo"]):
        if "periodo" in chunk.columns:
            tmp = pd.DataFrame()
            tmp["fecha"] = pd.to_datetime(
                chunk["periodo"].astype(str) + "01",
                format="%Y%m%d",
                errors="coerce"
            )
            tmp = tmp.dropna()
            fechas_acumuladas.append(tmp)

        del chunk
        gc.collect()

    if not fechas_acumuladas:
        print("dim_tiempo: sin fechas.")
        return

    dim = pd.concat(fechas_acumuladas, ignore_index=True).drop_duplicates()
    dim["fecha"] = pd.to_datetime(dim["fecha"])
    dim["anio"] = dim["fecha"].dt.year
    dim["trimestre"] = dim["fecha"].dt.quarter
    dim["mes"] = dim["fecha"].dt.month
    dim["nombre_mes"] = dim["fecha"].dt.month_name().map(MESES_ES).fillna(
        dim["fecha"].dt.month_name()
    )
    dim["dia"] = dim["fecha"].dt.day
    dim["semana"] = dim["fecha"].dt.isocalendar().week.astype(int)
    dim["fecha"] = dim["fecha"].dt.date

    cols = ["fecha", "anio", "trimestre", "mes", "nombre_mes", "dia", "semana"]
    dim = dim[cols].drop_duplicates(subset=["fecha"])

    existentes = pd.read_sql("SELECT fecha FROM dwh.dim_tiempo", engine)

    if not existentes.empty:
        existentes["fecha"] = pd.to_datetime(existentes["fecha"]).dt.date
        dim = dim[~dim["fecha"].isin(existentes["fecha"])]

    append_dwh(dim, "dim_tiempo")
    print(f"dim_tiempo cargada: {len(dim)} filas nuevas.")


def load_dim_ubicacion():
    print("Cargando dim_ubicacion...")

    cols = [
        "codigo_provincia", "provincia",
        "codigo_canton", "canton",
        "parroquia", "distrito", "circuito",
        "subcircuito", "zona", "area"
    ]

    acumulado = []

    for tabla in ["homicidio_limpia", "mdi_desaparecido_limpia"]:
        print(f"  Leyendo {tabla}...")

        for chunk in read_clean_chunks(tabla):
            tmp = pd.DataFrame()
            tmp["codigo_provincia"] = chunk.get("codigo_provincia")
            tmp["provincia"] = chunk.get("provincia")
            tmp["codigo_canton"] = chunk.get("codigo_canton")
            tmp["canton"] = chunk.get("canton")
            tmp["parroquia"] = chunk.get("parroquia") if "parroquia" in chunk.columns else None
            tmp["distrito"] = chunk.get("distrito")
            tmp["circuito"] = chunk.get("circuito")
            tmp["subcircuito"] = chunk.get("subcircuito")
            tmp["zona"] = chunk.get("zona")
            tmp["area"] = chunk.get("area_hecho") if "area_hecho" in chunk.columns else chunk.get("area")

            acumulado.append(clean_txt(tmp).drop_duplicates())

            del chunk, tmp
            gc.collect()

    print("  Leyendo mdi_arma_limpia...")

    for chunk in read_clean_chunks("mdi_arma_limpia"):
        tmp = pd.DataFrame()
        tmp["codigo_provincia"] = chunk.get("codigo_provincia")
        tmp["provincia"] = chunk.get("nombre_provincia")
        tmp["codigo_canton"] = chunk.get("codigo_canton")
        tmp["canton"] = chunk.get("nombre_canton")
        tmp["parroquia"] = chunk.get("nombre_parroquia")
        tmp["distrito"] = chunk.get("nombre_distrito")
        tmp["circuito"] = chunk.get("nombre_circuito")
        tmp["subcircuito"] = chunk.get("nombre_subcircuito")
        tmp["zona"] = chunk.get("zona")
        tmp["area"] = chunk.get("area")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo edg_limpia...")

    for chunk in read_clean_chunks("edg_limpia"):
        for prefijo in ["fall", "insc", "res"]:
            tmp = pd.DataFrame()
            tmp["codigo_provincia"] = None
            tmp["provincia"] = chunk.get(f"prov_{prefijo}")
            tmp["codigo_canton"] = None
            tmp["canton"] = chunk.get(f"cant_{prefijo}")
            tmp["parroquia"] = chunk.get(f"parr_{prefijo}")
            tmp["distrito"] = None
            tmp["circuito"] = None
            tmp["subcircuito"] = None
            tmp["zona"] = None
            tmp["area"] = chunk.get(f"area_{prefijo}") if f"area_{prefijo}" in chunk.columns else None

            acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk
        gc.collect()

    print("  Leyendo enemdu_limpia...")

    for chunk in read_clean_chunks("enemdu_limpia"):
        if "ciudad" not in chunk.columns:
            del chunk
            gc.collect()
            continue

        # ENEMDU no trae nombres de lugar: se resuelven con el catálogo DPA
        geo = dpa_from_codigos(chunk["ciudad"])

        tmp = pd.DataFrame(index=chunk.index)
        tmp["codigo_provincia"] = geo["codigo_provincia_join"]
        tmp["provincia"] = geo["provincia_join"]
        tmp["codigo_canton"] = geo["codigo_canton_join"]
        tmp["canton"] = geo["canton_join"]
        tmp["parroquia"] = None
        tmp["distrito"] = None
        tmp["circuito"] = None
        tmp["subcircuito"] = None
        tmp["zona"] = chunk.get("zona")
        tmp["area"] = chunk.get("area")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp, geo
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    # Provincia/cantón homogéneos entre fuentes (MDI, EDG, ENEMDU, DPA)
    dim = normalize_geo_frame(dim, ["provincia", "canton"])
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_ubicacion", cols)

    append_dwh(dim, "dim_ubicacion")
    print(f"dim_ubicacion cargada: {len(dim)} filas nuevas.")


def load_dim_persona():
    print("Cargando dim_persona...")

    cols = [
        "sexo", "genero", "edad", "rango_edad",
        "etnia", "estado_civil", "nacionalidad",
        "instruccion", "discapacidad", "nivel_educativo"
    ]

    acumulado = []

    print("  Leyendo homicidio_limpia...")

    for chunk in read_clean_chunks("homicidio_limpia", ["sexo", "genero", "edad", "etnia", "estado_civil", "nacionalidad", "instruccion", "discapacidad"]):
        tmp = pd.DataFrame()
        tmp["sexo"] = chunk.get("sexo")
        tmp["genero"] = chunk.get("genero")
        tmp["edad"] = pd.to_numeric(chunk.get("edad"), errors="coerce")
        tmp["rango_edad"] = tmp["edad"].apply(rango_edad)
        tmp["etnia"] = chunk.get("etnia")
        tmp["estado_civil"] = chunk.get("estado_civil")
        tmp["nacionalidad"] = chunk.get("nacionalidad")
        tmp["instruccion"] = chunk.get("instruccion")
        tmp["discapacidad"] = chunk.get("discapacidad")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo mdi_desaparecido_limpia...")

    for chunk in read_clean_chunks("mdi_desaparecido_limpia", ["sexo", "edad", "rango_edad", "etnia", "nacionalidad"]):
        tmp = pd.DataFrame()
        tmp["sexo"] = chunk.get("sexo")
        tmp["genero"] = None
        tmp["edad"] = pd.to_numeric(chunk.get("edad"), errors="coerce")
        tmp["rango_edad"] = chunk.get("rango_edad") if "rango_edad" in chunk.columns else tmp["edad"].apply(rango_edad)
        tmp["etnia"] = chunk.get("etnia")
        tmp["estado_civil"] = None
        tmp["nacionalidad"] = chunk.get("nacionalidad")
        tmp["instruccion"] = None
        tmp["discapacidad"] = None

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo edg_limpia...")

    for chunk in read_clean_chunks("edg_limpia", ["sexo", "edad", "etnia", "est_civil", "nac_fall", "niv_inst"]):
        tmp = pd.DataFrame()
        tmp["sexo"] = chunk.get("sexo")
        tmp["genero"] = None
        tmp["edad"] = pd.to_numeric(chunk.get("edad"), errors="coerce")
        tmp["rango_edad"] = tmp["edad"].apply(rango_edad)
        tmp["etnia"] = chunk.get("etnia")
        tmp["estado_civil"] = chunk.get("est_civil")
        tmp["nacionalidad"] = chunk.get("nac_fall")
        tmp["instruccion"] = chunk.get("niv_inst")
        tmp["discapacidad"] = None

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo enemdu_limpia...")

    for chunk in read_clean_chunks("enemdu_limpia", ["p02", "p03", "p06", "p10a"]):
        tmp = pd.DataFrame()
        tmp["sexo"] = chunk.get("p02")
        tmp["genero"] = None
        tmp["edad"] = pd.to_numeric(chunk.get("p03"), errors="coerce")
        tmp["rango_edad"] = tmp["edad"].apply(rango_edad)
        tmp["etnia"] = None
        tmp["estado_civil"] = chunk.get("p06")
        tmp["nacionalidad"] = None
        tmp["instruccion"] = chunk.get("p10a")
        tmp["discapacidad"] = None

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    if "nivel_educativo" not in dim.columns:
        dim["nivel_educativo"] = None
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_persona", cols)

    append_dwh(dim, "dim_persona")
    print(f"dim_persona cargada: {len(dim)} filas nuevas.")


def load_dim_geo_punto():
    print("Cargando dim_geo_punto...")

    cols = [
        "latitud", "longitud", "geo_status",
        "geo_error", "geo_source_level", "geo_ok_final"
    ]

    acumulado = []

    for tabla in ["homicidio_limpia", "mdi_arma_limpia"]:
        print(f"  Leyendo {tabla}...")

        for chunk in read_clean_chunks(tabla):
            tmp = pd.DataFrame()
            tmp["latitud"] = pd.to_numeric(chunk.get("latitud_final"), errors="coerce")
            tmp["longitud"] = pd.to_numeric(chunk.get("longitud_final"), errors="coerce")
            tmp["geo_status"] = chunk.get("geo_status")
            tmp["geo_error"] = chunk.get("geo_error")
            tmp["geo_source_level"] = chunk.get("geo_source_level")
            tmp["geo_ok_final"] = pd.to_numeric(chunk.get("geo_ok_final"), errors="coerce")

            acumulado.append(clean_txt(tmp).drop_duplicates())

            del chunk, tmp
            gc.collect()

    print("  Leyendo mdi_desaparecido_limpia...")

    for chunk in read_clean_chunks("mdi_desaparecido_limpia"):
        posibles = [
            ("latitud_final", "longitud_final", "geo_status", "geo_error", "geo_source_level", "geo_ok_final"),
            ("latitud_desaparicion_final", "longitud_desaparicion_final", "geo_desaparicion_status", "geo_desaparicion_error", "geo_desaparicion_source_level", "geo_desaparicion_ok_final"),
            ("latitud_localizacion_final", "longitud_localizacion_final", "geo_localizacion_status", "geo_localizacion_error", "geo_localizacion_source_level", "geo_localizacion_ok_final"),
        ]

        for lat, lon, status, error, source, ok in posibles:
            tmp = pd.DataFrame()
            tmp["latitud"] = pd.to_numeric(chunk.get(lat), errors="coerce")
            tmp["longitud"] = pd.to_numeric(chunk.get(lon), errors="coerce")
            tmp["geo_status"] = chunk.get(status)
            tmp["geo_error"] = chunk.get(error)
            tmp["geo_source_level"] = chunk.get(source)
            tmp["geo_ok_final"] = pd.to_numeric(chunk.get(ok), errors="coerce")

            tmp = tmp.dropna(subset=["latitud", "longitud"], how="all")
            acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = dim.dropna(subset=["latitud", "longitud"], how="all")
    dim = remove_existing(dim, "dim_geo_punto", cols)

    append_dwh(dim, "dim_geo_punto")
    print(f"dim_geo_punto cargada: {len(dim)} filas nuevas.")


def load_dim_arma():
    print("Cargando dim_arma...")

    cols = [
        "arma", "tipo_arma", "clase_arma",
        "calibre_estandarizado", "fabricacion",
        "nombre_objeto", "subtipo_objeto_robado"
    ]

    acumulado = []

    print("  Leyendo homicidio_limpia...")

    for chunk in read_clean_chunks("homicidio_limpia"):
        tmp = pd.DataFrame()
        tmp["arma"] = chunk.get("arma")
        tmp["tipo_arma"] = chunk.get("tipo_arma")
        tmp["clase_arma"] = None
        tmp["calibre_estandarizado"] = None
        tmp["fabricacion"] = None
        tmp["nombre_objeto"] = None
        tmp["subtipo_objeto_robado"] = None

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo mdi_arma_limpia...")

    for chunk in read_clean_chunks("mdi_arma_limpia"):
        tmp = pd.DataFrame()
        tmp["arma"] = None
        tmp["tipo_arma"] = None
        tmp["clase_arma"] = chunk.get("clase_arma")
        tmp["calibre_estandarizado"] = chunk.get("calibre_estandarizado")
        tmp["fabricacion"] = chunk.get("fabricacion")
        tmp["nombre_objeto"] = chunk.get("nombre_objeto")
        tmp["subtipo_objeto_robado"] = chunk.get("subtipo_objeto_robado")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_arma", cols)

    append_dwh(dim, "dim_arma")
    print(f"dim_arma cargada: {len(dim)} filas nuevas.")


def load_dim_delito():
    print("Cargando dim_delito...")

    cols = ["delito", "tipo_delito", "modalidad", "codigo_iccs"]
    acumulado = []

    for chunk in read_clean_chunks("mdi_arma_limpia"):
        tmp = pd.DataFrame()
        tmp["delito"] = chunk.get("delito")
        tmp["tipo_delito"] = chunk.get("tipo_delito")
        tmp["modalidad"] = chunk.get("modalidad")
        tmp["codigo_iccs"] = chunk.get("codigo_iccs")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_delito", cols)

    append_dwh(dim, "dim_delito")
    print(f"dim_delito cargada: {len(dim)} filas nuevas.")


def load_dim_motivacion():
    print("Cargando dim_motivacion...")

    cols = [
        "presunta_motivacion",
        "probable_causa_motivada",
        "presun_motiva_observada",
        "motivacion",
        "motivacion_observada",
        "motivacion_desaparicion_observada",
        "motivo_desaparicion"
    ]

    acumulado = []

    print("  Leyendo homicidio_limpia...")

    for chunk in read_clean_chunks("homicidio_limpia"):
        tmp = pd.DataFrame()
        tmp["presunta_motivacion"] = chunk.get("presunta_motivacion")
        tmp["probable_causa_motivada"] = chunk.get("probable_causa_motivada")
        tmp["presun_motiva_observada"] = chunk.get("presun_motiva_observada")
        tmp["motivacion"] = None
        tmp["motivacion_observada"] = None
        tmp["motivacion_desaparicion_observada"] = None
        tmp["motivo_desaparicion"] = None

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    print("  Leyendo mdi_desaparecido_limpia...")

    for chunk in read_clean_chunks("mdi_desaparecido_limpia"):
        tmp = pd.DataFrame()
        tmp["presunta_motivacion"] = None
        tmp["probable_causa_motivada"] = None
        tmp["presun_motiva_observada"] = None
        tmp["motivacion"] = chunk.get("motivacion")
        tmp["motivacion_observada"] = chunk.get("motivacion_observada")
        tmp["motivacion_desaparicion_observada"] = chunk.get("motivacion_desaparicion_observada")
        tmp["motivo_desaparicion"] = chunk.get("motivo_desaparicion")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_motivacion", cols)

    append_dwh(dim, "dim_motivacion")
    print(f"dim_motivacion cargada: {len(dim)} filas nuevas.")


def load_dim_estado_caso():
    print("Cargando dim_estado_caso...")

    cols = ["situacion_actual", "status"]
    acumulado = []

    for chunk in read_clean_chunks("mdi_desaparecido_limpia"):
        tmp = pd.DataFrame()
        tmp["situacion_actual"] = chunk.get("situacion_actual")
        tmp["status"] = chunk.get("status")

        acumulado.append(clean_txt(tmp).drop_duplicates())

        del chunk, tmp
        gc.collect()

    dim = pd.concat(acumulado, ignore_index=True)
    dim = clean_txt(dim[cols]).drop_duplicates()
    dim = fill_dim_text(dim)
    dim = remove_existing(dim, "dim_estado_caso", cols)

    append_dwh(dim, "dim_estado_caso")
    print(f"dim_estado_caso cargada: {len(dim)} filas nuevas.")
