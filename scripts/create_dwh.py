from sqlalchemy import text
from utils.config import engine


def create_dwh():
    sql = """
    CREATE SCHEMA IF NOT EXISTS dwh;

    DROP TABLE IF EXISTS dwh.fact_enemdu CASCADE;
    DROP TABLE IF EXISTS dwh.fact_defuncion CASCADE;
    DROP TABLE IF EXISTS dwh.fact_desaparicion CASCADE;
    DROP TABLE IF EXISTS dwh.fact_arma CASCADE;
    DROP TABLE IF EXISTS dwh.fact_homicidio CASCADE;

    DROP TABLE IF EXISTS dwh.dim_estado_caso CASCADE;
    DROP TABLE IF EXISTS dwh.dim_motivacion CASCADE;
    DROP TABLE IF EXISTS dwh.dim_delito CASCADE;
    DROP TABLE IF EXISTS dwh.dim_arma CASCADE;
    DROP TABLE IF EXISTS dwh.dim_geo_punto CASCADE;
    DROP TABLE IF EXISTS dwh.dim_persona CASCADE;
    DROP TABLE IF EXISTS dwh.dim_ubicacion CASCADE;
    DROP TABLE IF EXISTS dwh.dim_tiempo CASCADE;

    CREATE TABLE dwh.dim_tiempo (
        tiempo_key SERIAL PRIMARY KEY,
        fecha DATE UNIQUE,
        anio INT,
        trimestre INT,
        mes INT,
        nombre_mes VARCHAR(20),
        dia INT,
        semana INT
    );

    CREATE TABLE dwh.dim_ubicacion (
        ubicacion_key SERIAL PRIMARY KEY,
        codigo_provincia VARCHAR(50),
        provincia VARCHAR(150),
        codigo_canton VARCHAR(50),
        canton VARCHAR(150),
        parroquia VARCHAR(150),
        distrito VARCHAR(150),
        circuito VARCHAR(150),
        subcircuito VARCHAR(150),
        zona VARCHAR(100),
        area VARCHAR(100)
    );

    CREATE TABLE dwh.dim_persona (
        persona_key SERIAL PRIMARY KEY,
        sexo VARCHAR(50),
        edad INT,
        rango_edad VARCHAR(50),
        etnia VARCHAR(100),
        estado_civil VARCHAR(100),
        nacionalidad VARCHAR(100),
        instruccion VARCHAR(150),
        nivel_educativo VARCHAR(150),
        genero VARCHAR(100),
        discapacidad VARCHAR(100)
    );

    CREATE TABLE dwh.dim_geo_punto (
        geo_key SERIAL PRIMARY KEY,
        latitud NUMERIC(12,8),
        longitud NUMERIC(12,8),
        geo_status VARCHAR(100),
        geo_error VARCHAR(255),
        geo_source_level VARCHAR(100),
        geo_ok_final INT
    );

    CREATE TABLE dwh.dim_arma (
        arma_key SERIAL PRIMARY KEY,
        arma VARCHAR(150),
        tipo_arma VARCHAR(150),
        clase_arma VARCHAR(150),
        calibre_estandarizado VARCHAR(100),
        fabricacion VARCHAR(150),
        nombre_objeto VARCHAR(255),
        subtipo_objeto_robado VARCHAR(255)
    );

    CREATE TABLE dwh.dim_delito (
        delito_key SERIAL PRIMARY KEY,
        delito VARCHAR(255),
        tipo_delito VARCHAR(255),
        modalidad VARCHAR(255),
        codigo_iccs VARCHAR(255)
    );

    CREATE TABLE dwh.dim_motivacion (
        motivacion_key SERIAL PRIMARY KEY,
        presunta_motivacion VARCHAR(255),
        probable_causa_motivada VARCHAR(255),
        motivacion VARCHAR(255),
        motivo_desaparicion VARCHAR(255),
        motivacion_observada VARCHAR(255),
        motivacion_desaparicion_observada VARCHAR(255),
        presun_motiva_observada VARCHAR(255)
    );

    CREATE TABLE dwh.dim_estado_caso (
        estado_caso_key SERIAL PRIMARY KEY,
        situacion_actual VARCHAR(150),
        status VARCHAR(150)
    );

    CREATE TABLE dwh.fact_homicidio (
        homicidio_key BIGSERIAL PRIMARY KEY,
        tiempo_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        ubicacion_key INT REFERENCES dwh.dim_ubicacion(ubicacion_key),
        persona_key INT REFERENCES dwh.dim_persona(persona_key),
        geo_key INT REFERENCES dwh.dim_geo_punto(geo_key),
        arma_key INT REFERENCES dwh.dim_arma(arma_key),
        motivacion_key INT REFERENCES dwh.dim_motivacion(motivacion_key),
        tipo_muerte VARCHAR(150),
        lugar VARCHAR(150),
        tipo_lugar VARCHAR(150),
        area_hecho VARCHAR(100),
        conteo_homicidio INT DEFAULT 1
    );

    CREATE TABLE dwh.fact_arma (
        arma_evento_key BIGSERIAL PRIMARY KEY,
        tiempo_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        ubicacion_key INT REFERENCES dwh.dim_ubicacion(ubicacion_key),
        geo_key INT REFERENCES dwh.dim_geo_punto(geo_key),
        arma_key INT REFERENCES dwh.dim_arma(arma_key),
        delito_key INT REFERENCES dwh.dim_delito(delito_key),
        tipo_lugar VARCHAR(150),
        cantidad NUMERIC(18,2),
        conteo_evento INT DEFAULT 1
    );

    CREATE TABLE dwh.fact_desaparicion (
        desaparicion_key BIGSERIAL PRIMARY KEY,
        tiempo_desaparicion_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        tiempo_denuncia_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        tiempo_conocimiento_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        tiempo_localizacion_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        ubicacion_key INT REFERENCES dwh.dim_ubicacion(ubicacion_key),
        persona_key INT REFERENCES dwh.dim_persona(persona_key),
        geo_key INT REFERENCES dwh.dim_geo_punto(geo_key),
        motivacion_key INT REFERENCES dwh.dim_motivacion(motivacion_key),
        estado_caso_key INT REFERENCES dwh.dim_estado_caso(estado_caso_key),
        dias_solucion INT,
        conteo_desaparicion INT DEFAULT 1
    );

    CREATE TABLE dwh.fact_defuncion (
        defuncion_key BIGSERIAL PRIMARY KEY,
        tiempo_fallecimiento_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        tiempo_inscripcion_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        tiempo_nacimiento_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        ubicacion_key INT REFERENCES dwh.dim_ubicacion(ubicacion_key),
        persona_key INT REFERENCES dwh.dim_persona(persona_key),
        causa VARCHAR(255),
        causa103 VARCHAR(255),
        causa4 VARCHAR(255),
        causa67a VARCHAR(255),
        causa67b VARCHAR(255),
        causa80 VARCHAR(255),
        lugar_ocur VARCHAR(255),
        lug_viol VARCHAR(255),
        mor_viol VARCHAR(255),
        autopsia VARCHAR(50),
        conteo_defuncion INT DEFAULT 1
    );

    CREATE TABLE dwh.fact_enemdu (
        enemdu_key BIGSERIAL PRIMARY KEY,
        tiempo_key INT REFERENCES dwh.dim_tiempo(tiempo_key),
        ubicacion_key INT REFERENCES dwh.dim_ubicacion(ubicacion_key),
        persona_key INT REFERENCES dwh.dim_persona(persona_key),
        id_vivienda VARCHAR(100),
        id_hogar VARCHAR(100),
        id_persona VARCHAR(100),
        periodo VARCHAR(50),
        fexp NUMERIC(18,4),
        ingrl NUMERIC(18,2),
        ingpc NUMERIC(18,2),
        empleo VARCHAR(100),
        desempleo VARCHAR(100),
        subempleo VARCHAR(100),
        sector VARCHAR(100),
        pobreza VARCHAR(100),
        pobreza_extrema VARCHAR(100),
        conteo_persona INT DEFAULT 1
    );
    """

    with engine.begin() as conn:
        conn.execute(text(sql))

    print("DWH creado correctamente.")
