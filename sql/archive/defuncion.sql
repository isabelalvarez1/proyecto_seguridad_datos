-- Referencia histórica. La definición vigente está en scripts/create_cubes.py.
CREATE MATERIALIZED VIEW dwh.cubo_defuncion AS
SELECT
    dt_fall.anio                          AS anio_fallecimiento,
    dt_fall.mes                           AS mes_fallecimiento,
    dt_fall.nombre_mes                    AS nombre_mes_fallecimiento,

    dt_nac.anio                           AS anio_nacimiento,

    du.provincia,
    du.canton,
    du.area,

    dp.sexo,
    dp.rango_edad,
    dp.etnia,
    dp.estado_civil,
    dp.nacionalidad,
    dp.instruccion,

    fd.causa,
    fd.causa103,
    fd.causa4,
    fd.causa67a,
    fd.lugar_ocur,
    fd.lug_viol,
    fd.mor_viol,
    fd.autopsia,

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

CREATE UNIQUE INDEX idx_cubo_defuncion_unique
ON dwh.cubo_defuncion (
    anio_fallecimiento, mes_fallecimiento,
    provincia, canton,
    sexo, rango_edad, causa, mor_viol
);

CREATE INDEX idx_cubo_def_tiempo
ON dwh.cubo_defuncion (anio_fallecimiento, mes_fallecimiento);

CREATE INDEX idx_cubo_def_geo
ON dwh.cubo_defuncion (provincia, canton);
