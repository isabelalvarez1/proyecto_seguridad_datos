#### para consultar los campos de una tabla fact###
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'fact_homicidio'
ORDER BY ordinal_position;
##### obtener los campos de las tablas dimensiones####
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'dim_motivacion'
ORDER BY ordinal_position;
#####  Crear el cubo de homicidios  que es una vista materializada####
CREATE MATERIALIZED VIEW dwh.cubo_homicidio AS
SELECT
    -- TIEMPO
    dt.anio,
    dt.trimestre,
    dt.mes,
    dt.nombre_mes,
    dt.semana,

    -- UBICACIÓN
    du.provincia,
    du.canton,
    du.parroquia,
    du.distrito,
    du.circuito,
    du.zona,
    du.area,

    -- PERSONA
    dp.sexo,
    dp.rango_edad,
    dp.etnia,
    dp.instruccion,
    dp.nivel_educativo,
    dp.nacionalidad,

    -- ARMA
    da.tipo_arma,
    da.clase_arma,
    da.arma,

    -- MOTIVACIÓN
    dm.motivacion,
    dm.presunta_motivacion,

    -- CAMPOS PROPIOS DEL HECHO
    fh.tipo_muerte,
    fh.tipo_lugar,
    fh.area_hecho,

    -- MÉTRICAS
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
##### Crear indices de homicidios####
CREATE UNIQUE INDEX idx_cubo_homicidio_unique
ON dwh.cubo_homicidio (
    anio, mes, provincia, canton,
    sexo, rango_edad, tipo_arma, motivacion, tipo_muerte
);

CREATE INDEX idx_cubo_hom_tiempo 
ON dwh.cubo_homicidio (anio, mes);

CREATE INDEX idx_cubo_hom_geo 
ON dwh.cubo_homicidio (provincia, canton);

CREATE INDEX idx_cubo_hom_persona 
ON dwh.cubo_homicidio (sexo, rango_edad, etnia);

CREATE INDEX idx_cubo_hom_arma 
ON dwh.cubo_homicidio (tipo_arma, clase_arma);