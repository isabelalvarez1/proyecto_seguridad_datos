### obtener los campos de fact_desaparicion
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'dwh'
  AND table_name = 'fact_desaparicion'
ORDER BY ordinal_position;
### obtener los campos de cada dimension que interviene, las demas ya estan en homicidio, solo se agregara la nueva
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'dwh'
  AND table_name = 'dim_estado_caso'
ORDER BY ordinal_position;
### Creacion del cubo desaparicion##
CREATE MATERIALIZED VIEW dwh.cubo_desaparicion AS
SELECT
    -- TIEMPO DESAPARICIÓN
    dt_des.anio                         AS anio_desaparicion,
    dt_des.trimestre                    AS trimestre_desaparicion,
    dt_des.mes                          AS mes_desaparicion,
    dt_des.nombre_mes                   AS nombre_mes_desaparicion,

    -- TIEMPO DENUNCIA
    dt_den.anio                         AS anio_denuncia,
    dt_den.mes                          AS mes_denuncia,

    -- TIEMPO LOCALIZACIÓN
    dt_loc.anio                         AS anio_localizacion,
    dt_loc.mes                          AS mes_localizacion,

    -- UBICACIÓN
    du.provincia,
    du.canton,
    du.parroquia,
    du.zona,
    du.area,

    -- PERSONA
    dp.sexo,
    dp.rango_edad,
    dp.etnia,
    dp.instruccion,
    dp.nacionalidad,

    -- MOTIVACIÓN
    dm.motivacion,
    dm.motivo_desaparicion,
    dm.motivacion_desaparicion_observada,

    -- ESTADO DEL CASO
    de.situacion_actual,
    de.status,

    -- MÉTRICAS
    SUM(fd.conteo_desaparicion)                         AS total_desapariciones,
    AVG(fd.dias_solucion)                               AS promedio_dias_solucion,
    MIN(fd.dias_solucion)                               AS min_dias_solucion,
    MAX(fd.dias_solucion)                               AS max_dias_solucion,
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
    dm.motivacion, dm.motivo_desaparicion, dm.motivacion_desaparicion_observada,
    de.situacion_actual, de.status;
### creacion de indices
-- Índice único (para REFRESH CONCURRENTLY)
CREATE UNIQUE INDEX idx_cubo_desaparicion_unique
ON dwh.cubo_desaparicion (
    anio_desaparicion, mes_desaparicion,
    provincia, canton, parroquia,
    sexo, rango_edad, etnia,
    motivacion, motivo_desaparicion,
    situacion_actual, status
);
-- Filtros temporales
CREATE INDEX idx_cubo_des_tiempo
ON dwh.cubo_desaparicion (anio_desaparicion, mes_desaparicion);

-- Filtros geográficos
CREATE INDEX idx_cubo_des_geo
ON dwh.cubo_desaparicion (provincia, canton);

-- Filtros de persona
CREATE INDEX idx_cubo_des_persona
ON dwh.cubo_desaparicion (sexo, rango_edad, etnia);

-- Filtros de estado
CREATE INDEX idx_cubo_des_estado
ON dwh.cubo_desaparicion (situacion_actual, status);
### para refrescar el cubo 
REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.cubo_desaparicion;