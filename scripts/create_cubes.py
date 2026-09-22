"""
Creación y refresh de cubos OLAP (vistas materializadas).
"""
from sqlalchemy import text
from utils.config import engine

CUBOS_SQL = {
    "cubo_homicidio": """
        DROP MATERIALIZED VIEW IF EXISTS dwh.cubo_homicidio CASCADE;
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
            fh.tipo_muerte, fh.tipo_lugar, fh.area_hecho;
    """,
    "cubo_arma": """
        DROP MATERIALIZED VIEW IF EXISTS dwh.cubo_arma CASCADE;
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
            fa.tipo_lugar;
    """,
    "cubo_desaparicion": """
        DROP MATERIALIZED VIEW IF EXISTS dwh.cubo_desaparicion CASCADE;
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
            de.situacion_actual, de.status;
    """,
    "cubo_defuncion": """
        DROP MATERIALIZED VIEW IF EXISTS dwh.cubo_defuncion CASCADE;
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
            fd.lugar_ocur, fd.lug_viol, fd.mor_viol, fd.autopsia;
    """,
}


def refresh_all_cubes():
    """Crea (o recrea) todos los cubos OLAP."""
    with engine.begin() as conn:
        for nombre, sql in CUBOS_SQL.items():
            print(f"  Creando {nombre}...")
            conn.execute(text(sql))
            print(f"  {nombre} creado OK.")
    print("Todos los cubos creados.")
