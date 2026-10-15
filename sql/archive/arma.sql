-- Referencia histórica. La definición vigente está en scripts/create_cubes.py.
CREATE MATERIALIZED VIEW dwh.cubo_arma AS
SELECT
    dt.anio,
    dt.trimestre,
    dt.mes,
    dt.nombre_mes,

    du.provincia,
    du.canton,
    du.zona,
    du.area,

    da.clase_arma,
    da.calibre_estandarizado,
    da.fabricacion,
    da.nombre_objeto,
    da.subtipo_objeto_robado,

    dd.delito,
    dd.tipo_delito,
    dd.modalidad,

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

CREATE UNIQUE INDEX idx_cubo_arma_unique
ON dwh.cubo_arma (
    anio, mes, provincia, canton,
    clase_arma, delito, tipo_delito
);

CREATE INDEX idx_cubo_arma_tiempo
ON dwh.cubo_arma (anio, mes);

CREATE INDEX idx_cubo_arma_geo
ON dwh.cubo_arma (provincia, canton);
