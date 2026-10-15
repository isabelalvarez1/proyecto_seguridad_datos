"""
Creación y refresh de cubos OLAP (vistas materializadas).

Diseño pensado para Power BI:
  * Los cubos se REFRESCAN (no se borran) para que las vistas dependientes
    `dwh.v_cubo_*` sobrevivan a cada refresh. Antes se hacía
    `DROP MATERIALIZED VIEW ... CASCADE`, que borraba esas vistas y por eso
    Power BI reportaba que `v_cubo_arma` ya no existía.
  * Se publica además una vista envoltorio por cubo, porque el conector de
    Power BI enumera vistas normales pero NO las vistas materializadas.
"""
from sqlalchemy import text
from utils.config import engine

CUBOS_SQL = {
    "cubo_homicidio": """
        CREATE MATERIALIZED VIEW dwh.cubo_homicidio AS
        SELECT
            dt.anio, dt.trimestre, dt.mes, dt.nombre_mes, dt.semana,
            du.provincia, du.canton, du.parroquia, du.distrito,
            du.circuito, du.zona, du.area,
            dp.sexo, dp.rango_edad, dp.etnia, dp.instruccion,
            dp.nivel_educativo, dp.nacionalidad,
            da.tipo_arma, da.clase_arma, da.arma,
            dm.motivacion, dm.presunta_motivacion,
            fh.tipo_muerte, fh.tipo_lugar, fh.area_hecho,
            SUM(fh.conteo_homicidio) AS total_homicidios
        FROM dwh.fact_homicidio fh
        JOIN dwh.dim_tiempo      dt ON fh.tiempo_key     = dt.tiempo_key
        JOIN dwh.dim_ubicacion   du ON fh.ubicacion_key  = du.ubicacion_key
        JOIN dwh.dim_persona     dp ON fh.persona_key    = dp.persona_key
        JOIN dwh.dim_arma        da ON fh.arma_key       = da.arma_key
        JOIN dwh.dim_motivacion  dm ON fh.motivacion_key = dm.motivacion_key
        GROUP BY
            dt.anio, dt.trimestre, dt.mes, dt.nombre_mes, dt.semana,
            du.provincia, du.canton, du.parroquia, du.distrito,
            du.circuito, du.zona, du.area,
            dp.sexo, dp.rango_edad, dp.etnia, dp.instruccion,
            dp.nivel_educativo, dp.nacionalidad,
            da.tipo_arma, da.clase_arma, da.arma,
            dm.motivacion, dm.presunta_motivacion,
            fh.tipo_muerte, fh.tipo_lugar, fh.area_hecho
        WITH NO DATA
    """,
    "cubo_arma": """
        CREATE MATERIALIZED VIEW dwh.cubo_arma AS
        SELECT
            dt.anio, dt.trimestre, dt.mes, dt.nombre_mes,
            du.provincia, du.canton, du.zona, du.area,
            da.clase_arma, da.calibre_estandarizado, da.fabricacion,
            da.nombre_objeto, da.subtipo_objeto_robado,
            dd.delito, dd.tipo_delito, dd.modalidad,
            fa.tipo_lugar,
            SUM(fa.conteo_evento) AS total_eventos,
            SUM(fa.cantidad)      AS total_armas
        FROM dwh.fact_arma fa
        JOIN dwh.dim_tiempo    dt ON fa.tiempo_key    = dt.tiempo_key
        JOIN dwh.dim_ubicacion du ON fa.ubicacion_key = du.ubicacion_key
        JOIN dwh.dim_arma      da ON fa.arma_key      = da.arma_key
        JOIN dwh.dim_delito    dd ON fa.delito_key    = dd.delito_key
        GROUP BY
            dt.anio, dt.trimestre, dt.mes, dt.nombre_mes,
            du.provincia, du.canton, du.zona, du.area,
            da.clase_arma, da.calibre_estandarizado, da.fabricacion,
            da.nombre_objeto, da.subtipo_objeto_robado,
            dd.delito, dd.tipo_delito, dd.modalidad,
            fa.tipo_lugar
        WITH NO DATA
    """,
    "cubo_desaparicion": """
        CREATE MATERIALIZED VIEW dwh.cubo_desaparicion AS
        SELECT
            dt_des.anio                         AS anio_desaparicion,
            dt_des.trimestre                    AS trimestre_desaparicion,
            dt_des.mes                          AS mes_desaparicion,
            dt_des.nombre_mes                   AS nombre_mes_desaparicion,
            dt_den.anio                         AS anio_denuncia,
            dt_den.mes                          AS mes_denuncia,
            dt_loc.anio                         AS anio_localizacion,
            dt_loc.mes                          AS mes_localizacion,
            du.provincia, du.canton, du.parroquia, du.zona, du.area,
            dp.sexo, dp.rango_edad, dp.etnia, dp.instruccion, dp.nacionalidad,
            dm.motivacion, dm.motivo_desaparicion,
            dm.motivacion_desaparicion_observada,
            de.situacion_actual, de.status,
            SUM(fd.conteo_desaparicion)                         AS total_desapariciones,
            AVG(fd.dias_solucion)                               AS promedio_dias_solucion,
            SUM(CASE WHEN de.situacion_actual = 'LOCALIZADO'
                     THEN fd.conteo_desaparicion ELSE 0 END)    AS total_localizados,
            ROUND(
                SUM(CASE WHEN de.situacion_actual = 'LOCALIZADO'
                         THEN fd.conteo_desaparicion ELSE 0 END) * 100.0
                / NULLIF(SUM(fd.conteo_desaparicion), 0), 2)   AS tasa_localizacion_pct
        FROM dwh.fact_desaparicion fd
        JOIN dwh.dim_tiempo       dt_des ON fd.tiempo_desaparicion_key = dt_des.tiempo_key
        JOIN dwh.dim_tiempo       dt_den ON fd.tiempo_denuncia_key     = dt_den.tiempo_key
        JOIN dwh.dim_tiempo       dt_loc ON fd.tiempo_localizacion_key = dt_loc.tiempo_key
        JOIN dwh.dim_ubicacion    du     ON fd.ubicacion_key           = du.ubicacion_key
        JOIN dwh.dim_persona      dp     ON fd.persona_key             = dp.persona_key
        JOIN dwh.dim_motivacion   dm     ON fd.motivacion_key          = dm.motivacion_key
        JOIN dwh.dim_estado_caso  de     ON fd.estado_caso_key         = de.estado_caso_key
        GROUP BY
            dt_des.anio, dt_des.trimestre, dt_des.mes, dt_des.nombre_mes,
            dt_den.anio, dt_den.mes,
            dt_loc.anio, dt_loc.mes,
            du.provincia, du.canton, du.parroquia, du.zona, du.area,
            dp.sexo, dp.rango_edad, dp.etnia, dp.instruccion, dp.nacionalidad,
            dm.motivacion, dm.motivo_desaparicion,
            dm.motivacion_desaparicion_observada,
            de.situacion_actual, de.status
        WITH NO DATA
    """,
    "cubo_defuncion": """
        CREATE MATERIALIZED VIEW dwh.cubo_defuncion AS
        SELECT
            dt_fall.anio                          AS anio_fallecimiento,
            dt_fall.mes                           AS mes_fallecimiento,
            dt_fall.nombre_mes                    AS nombre_mes_fallecimiento,
            dt_nac.anio                           AS anio_nacimiento,
            du.provincia, du.canton, du.area,
            dp.sexo, dp.rango_edad, dp.etnia,
            dp.estado_civil, dp.nacionalidad, dp.instruccion,
            fd.causa, fd.causa103, fd.causa4, fd.causa67a,
            fd.lugar_ocur, fd.lug_viol, fd.mor_viol, fd.autopsia,
            SUM(fd.conteo_defuncion)              AS total_defunciones,
            SUM(CASE WHEN fd.mor_viol = 'SI'
                     THEN fd.conteo_defuncion ELSE 0 END) AS muertes_violentas
        FROM dwh.fact_defuncion fd
        JOIN dwh.dim_tiempo    dt_fall ON fd.tiempo_fallecimiento_key = dt_fall.tiempo_key
        JOIN dwh.dim_tiempo    dt_nac  ON fd.tiempo_nacimiento_key    = dt_nac.tiempo_key
        JOIN dwh.dim_ubicacion du      ON fd.ubicacion_key            = du.ubicacion_key
        JOIN dwh.dim_persona   dp      ON fd.persona_key              = dp.persona_key
        GROUP BY
            dt_fall.anio, dt_fall.mes, dt_fall.nombre_mes,
            dt_nac.anio,
            du.provincia, du.canton, du.area,
            dp.sexo, dp.rango_edad, dp.etnia, dp.estado_civil,
            dp.nacionalidad, dp.instruccion,
            fd.causa, fd.causa103, fd.causa4, fd.causa67a,
            fd.lugar_ocur, fd.lug_viol, fd.mor_viol, fd.autopsia
        WITH NO DATA
    """,
    # Reconstruido desde el DWH (fact_enemdu + dim_ubicacion) en vez de
    # clean.enemdu_limpia + catalogo.dpa_ecuador: así usa el MISMO vocabulario
    # de provincia/cantón que el resto de cubos y Power BI puede cruzarlos.
    # Además el join anterior con el DPA duplicaba el cantón 2201 (2 filas).
    "cubo_socioeconomico": """
        CREATE MATERIALIZED VIEW dwh.cubo_socioeconomico AS
        SELECT
            LEFT(fe.periodo, 4)::integer                     AS anio,
            RIGHT(fe.periodo, 2)::integer                    AS mes,
            fe.periodo,
            du.provincia,
            du.canton,
            fe.pobreza,
            fe.empleo,
            COALESCE(fe.sector, 'SIN_DATO')                  AS sector,
            COUNT(*)                                         AS total_personas,
            AVG(fe.ingpc::numeric)                           AS ingreso_per_capita,
            AVG(fe.ingrl::numeric)                           AS ingreso_laboral,
            SUM(CASE WHEN fe.pobreza = 'POBRE'
                     THEN 1 ELSE 0 END)                      AS total_pobres,
            SUM(CASE WHEN fe.pobreza = 'NO POBRE'
                     THEN 1 ELSE 0 END)                      AS total_no_pobres,
            ROUND(
                SUM(CASE WHEN fe.pobreza = 'POBRE' THEN 1 ELSE 0 END)::numeric
                * 100.0 / NULLIF(COUNT(*), 0)::numeric, 2)   AS tasa_pobreza_pct,
            SUM(CASE WHEN fe.empleo = 'POBLACIÓN CON EMPLEO'
                     THEN 1 ELSE 0 END)                      AS total_con_empleo,
            ROUND(
                SUM(CASE WHEN fe.empleo = 'POBLACIÓN CON EMPLEO'
                         THEN 1 ELSE 0 END)::numeric
                * 100.0 / NULLIF(COUNT(*), 0)::numeric, 2)   AS tasa_empleo_pct
        FROM dwh.fact_enemdu fe
        JOIN dwh.dim_ubicacion du ON fe.ubicacion_key = du.ubicacion_key
        WHERE fe.periodo IS NOT NULL
          AND fe.periodo <> 'SIN_DATO'
          AND LENGTH(fe.periodo) = 6
        GROUP BY
            LEFT(fe.periodo, 4), RIGHT(fe.periodo, 2), fe.periodo,
            du.provincia, du.canton, fe.pobreza, fe.empleo, fe.sector
        WITH NO DATA
    """,
    # Un registro por provincia y año compartidos. Agregar cada fuente ANTES
    # de unirlas impide multiplicar homicidios por registros de la encuesta.
    # Los encuestados no son la población total: no calcular aquí tasas por
    # 100.000 habitantes a partir del tamaño de la muestra ENEMDU.
    "cubo_seguridad_economia": """
        CREATE MATERIALIZED VIEW dwh.cubo_seguridad_economia AS
        WITH homicidios AS (
            SELECT anio, provincia,
                   SUM(total_homicidios) AS total_homicidios
            FROM dwh.cubo_homicidio
            WHERE provincia <> 'SIN_DATO'
            GROUP BY anio, provincia
        ), economia AS (
            SELECT LEFT(fe.periodo, 4)::integer AS anio,
                   du.provincia,
                   COUNT(*) AS personas_encuestadas,
                   SUM(CASE WHEN fe.pobreza = 'POBRE' THEN 1 ELSE 0 END) AS total_pobres,
                   ROUND(SUM(CASE WHEN fe.pobreza = 'POBRE' THEN 1 ELSE 0 END)
                         * 100.0 / NULLIF(COUNT(*), 0), 2) AS tasa_pobreza_pct,
                   SUM(CASE WHEN fe.empleo = 'POBLACIÓN CON EMPLEO' THEN 1 ELSE 0 END)
                       AS total_con_empleo,
                   ROUND(SUM(CASE WHEN fe.empleo = 'POBLACIÓN CON EMPLEO' THEN 1 ELSE 0 END)
                         * 100.0 / NULLIF(COUNT(*), 0), 2) AS tasa_empleo_pct,
                   AVG(fe.ingpc::numeric) AS ingreso_per_capita,
                   AVG(fe.ingrl::numeric) AS ingreso_laboral
            FROM dwh.fact_enemdu fe
            JOIN dwh.dim_ubicacion du ON fe.ubicacion_key = du.ubicacion_key
            WHERE fe.periodo ~ '^\\d{6}$'
              AND du.provincia <> 'SIN_DATO'
            GROUP BY LEFT(fe.periodo, 4), du.provincia
        )
        SELECT h.anio, h.provincia, h.total_homicidios,
               e.personas_encuestadas, e.total_pobres, e.tasa_pobreza_pct,
               e.total_con_empleo, e.tasa_empleo_pct,
               e.ingreso_per_capita, e.ingreso_laboral
        FROM homicidios h
        JOIN economia e USING (anio, provincia)
        WITH NO DATA
    """,
}

# Vistas envoltorio: lo único que Power BI lista en su navegador de tablas.
VISTAS_SQL = {
    nombre: f"CREATE OR REPLACE VIEW dwh.v_{nombre} AS SELECT * FROM dwh.{nombre};"
    for nombre in CUBOS_SQL
}


def _cubo_existe(conn, nombre: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM pg_matviews WHERE schemaname = 'dwh' AND matviewname = :n"
        ),
        {"n": nombre},
    ).first()
    return row is not None


def refresh_all_cubes():
    """Crea los cubos si faltan; en caso contrario solo los REFRESCA."""
    with engine.begin() as conn:
        for nombre, sql in CUBOS_SQL.items():
            creado = False
            if not _cubo_existe(conn, nombre):
                print(f"  Creando {nombre}...")
                conn.execute(text(sql + ";"))
                creado = True
            else:
                print(f"  Refrescando {nombre}...")
            # Siempre se refresca: garantiza datos aunque el cubo se acabe de crear
            # (se crea con WITH NO DATA para construirlo una sola vez).
            conn.execute(text(f"REFRESH MATERIALIZED VIEW dwh.{nombre}"))
            print(f"  {nombre} OK{' (nuevo)' if creado else ''}.")

        print("  Publicando vistas v_cubo_* ...")
        for sql in VISTAS_SQL.values():
            conn.execute(text(sql))
        print("  Vistas v_cubo_* OK.")
    print(f"Cubos OLAP listos ({len(CUBOS_SQL)} cubos + {len(VISTAS_SQL)} vistas).")


def drop_all_cubes():
    """Borra cubos y vistas (solo para reconstrucción total)."""
    with engine.begin() as conn:
        # El cubo combinado depende de homicidios: eliminar dependientes primero.
        for nombre in reversed(CUBOS_SQL):
            conn.execute(text(f"DROP VIEW IF EXISTS dwh.v_{nombre};"))
            conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS dwh.{nombre};"))
    print("Cubos eliminados.")


if __name__ == "__main__":
    refresh_all_cubes()
