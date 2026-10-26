"""Selección analítica explícita: vistas normales, sin DML ni imputación estadística."""
from dataclasses import dataclass

from utils.cleaning import PROVINCIAS_CANONICAS
from utils.validation_sql import ident, literal, sql_list, canonical_province


SCHEMA = 'analitica'
OWNER_TAG = 'Managed by scripts/create_analytic_views.py; contract=1'
PROVINCES = tuple(dict.fromkeys(PROVINCIAS_CANONICAS[key] for key in (
    'AZUAY', 'BOLIVAR', 'CANAR', 'CARCHI', 'COTOPAXI', 'CHIMBORAZO', 'EL ORO',
    'ESMERALDAS', 'GUAYAS', 'IMBABURA', 'LOJA', 'LOS RIOS', 'MANABI', 'MORONA SANTIAGO',
    'NAPO', 'PASTAZA', 'PICHINCHA', 'TUNGURAHUA', 'ZAMORA CHINCHIPE', 'GALAPAGOS',
    'SUCUMBIOS', 'ORELLANA', 'SANTO DOMINGO DE LOS TSACHILAS', 'SANTA ELENA')))


@dataclass(frozen=True)
class Field:
    name: str
    sql: str
    inputs: tuple
    role: str
    description: str
    missing: str = 'Conservar NULL y consultar estado; sin imputación estadística.'


@dataclass(frozen=True)
class AnalyticView:
    name: str
    table: str
    grain: str
    purpose: str
    fields: tuple
    join: str = ''

    @property
    def sql(self):
        selected = ',\n    '.join(f'{field.sql} AS {ident(field.name)}' for field in self.fields)
        return f'SELECT\n    {selected}\nFROM clean.{ident(self.table)} c\n{self.join}'

    @property
    def required(self):
        return {column for field in self.fields for column in field.inputs}


def direct(name, source=None, role='principal', description=None, missing=None):
    source = source or name
    return Field(name, 'c.' + ident(source), (source,), role, description or name.replace('_', ' '),
                 missing or 'Conservar NULL y consultar estado; sin imputación estadística.')


def date_fields(source, label='fecha'):
    return (
        direct(label, source, description='Fecha observada/interpretada; no sustituir fechas ausentes.'),
        Field('anio', f'extract(year from c.{ident(source)})::integer', (source,), 'principal', 'Año de la fecha de referencia.'),
        Field('mes', f'extract(month from c.{ident(source)})::integer', (source,), 'principal', 'Mes de la fecha de referencia.'),
    )


def age_group(expression):
    return f"""CASE WHEN {expression} >= 0 AND {expression} < 12 THEN '0-11'
        WHEN {expression} >= 12 AND {expression} < 18 THEN '12-17'
        WHEN {expression} >= 18 AND {expression} < 30 THEN '18-29'
        WHEN {expression} >= 30 AND {expression} < 45 THEN '30-44'
        WHEN {expression} >= 45 AND {expression} < 65 THEN '45-64'
        WHEN {expression} >= 65 AND {expression} <= 120 THEN '65+' END"""


def demographics(sex='sexo', age_state='edad_estado', open_age=False):
    group = age_group('c.edad_anios')
    group_inputs = ('edad_anios',)
    if open_age:
        group = f"CASE WHEN c.edad_censurada AND c.edad_limite_inferior>=65 THEN '65+' ELSE {group} END"
        group_inputs += ('edad_censurada', 'edad_limite_inferior')
    return (
        direct('sexo', sex),
        Field('edad_anios', 'CASE WHEN c.edad_anios BETWEEN 0 AND 120 THEN c.edad_anios END',
              ('edad_anios',), 'principal', 'Edad exacta en años; no incluye edad abierta ni otras unidades.'),
        direct('edad_estado', age_state, role='control'),
        Field('grupo_edad', group, group_inputs, 'principal',
              'Grupo de edad por límites explícitos; no inventa edad exacta.'),
    )


def geography(province='provincia', canton='canton', codes=True):
    fields = [direct('provincia', province), direct('canton', canton),
              Field('provincia_reconocida', f'COALESCE(c.{ident(province)} IN ({sql_list(PROVINCES)}),FALSE)',
                    (province,), 'control', 'Nombre reconocido entre las 24 provincias; no valida todo el territorio.')]
    if codes:
        fields.extend([direct('codigo_provincia', role='control'), direct('codigo_canton', role='control')])
    return tuple(fields)


def provenance(with_file=True):
    fields = [direct('version_clean', '_clean_run_id', role='procedencia', description='Versión de limpieza; no es predictor.')]
    if with_file:
        fields.append(direct('fuente_archivo', 'source_file', role='procedencia', description='Archivo de procedencia; no es predictor.'))
    return tuple(fields)


DURATION = 'CASE WHEN c.fecha_localizacion >= c.fecha_desaparicion THEN c.fecha_localizacion - c.fecha_desaparicion END'
EDG_INFANT = """((c.cod_edad IN ('DÍAS','DIAS') AND c.edad >= 0 AND c.edad < 365)
    OR (c.cod_edad = 'MESES' AND c.edad >= 0 AND c.edad < 12)
    OR (c.cod_edad = 'HORAS' AND c.edad >= 0 AND c.edad < 8760))"""
SURVEY_PROVINCE = 'COALESCE(c.provincia, p.provincia)'


VIEWS = (
    AnalyticView('v_homicidios', 'homicidio_limpia', 'Un registro de la fuente; no presupone evento único ni deduplicación.',
                 'Evolución, concentración territorial y perfil demográfico de homicidios registrados.',
                 date_fields('fecha_infraccion') + geography() + demographics() + (
                     direct('sexo_estado', role='control'), direct('tipo_muerte'), direct('arma'),
                     direct('tipo_arma', role='condicional', description='Detalle del arma; cobertura limitada, no sustituir con moda.'),
                     direct('tipo_arma_estado', role='control'), direct('area_hecho'), direct('tipo_lugar'),
                     direct('presunta_motivacion', role='condicional', description='Clasificación reportada; no equivale a causalidad comprobada.'),
                 ) + provenance()),
    AnalyticView('v_armas', 'mdi_arma_limpia', 'Un registro de la fuente de incautaciones; no equivale automáticamente a un evento único.',
                 'Evolución territorial de registros y cantidades observadas, con disponibilidad explícita.',
                 date_fields('fecha_evento') + geography('nombre_provincia', 'nombre_canton') + (
                     direct('clase_arma'), direct('clase_arma_estado', role='control'), direct('nombre_objeto'),
                     direct('cantidad', missing='No imputar cantidades; las 9.900 ausencias de 2025 son estructurales.'),
                     direct('cantidad_estado', role='control'),
                     Field('cantidad_observada', 'c.cantidad IS NOT NULL', ('cantidad',), 'control', 'Indica si se dispone de cantidad, no el número de eventos.'),
                     direct('delito', role='condicional'), direct('tipo_delito', role='condicional'), direct('tipo_lugar'),
                 ) + provenance()),
    AnalyticView('v_desapariciones', 'mdi_desaparecido_limpia', 'Un registro de desaparición de la fuente; conserva abiertos y cerrados.',
                 'Evolución, demografía, situación reportada y duraciones observables.',
                 date_fields('fecha_desaparicion', 'fecha_desaparicion') + geography(codes=False) + demographics() + (
                     direct('fecha_denuncia'), direct('fecha_localizacion'), direct('fecha_localizacion_estado', role='control'),
                     direct('situacion_actual', description='Estado original normalizado; ENCONTRADO, LOCALIZADO y FALLECIDO no se mezclan.'),
                     Field('dias_hasta_localizacion', DURATION, ('fecha_localizacion', 'fecha_desaparicion'), 'principal',
                           'Diferencia de días calendario cuando ambas fechas son observadas y están ordenadas.',
                           'Derivación determinista, no imputación; no completar casos abiertos.'),
                     direct('dias_solucion_reportados', 'dias_solucion', role='control'),
                     Field('duracion_origen', f"""CASE WHEN ({DURATION}) IS NULL THEN 'NO_OBSERVABLE'
                         WHEN c.dias_solucion IS NULL THEN 'CALCULADA_FECHAS'
                         WHEN c.dias_solucion = ({DURATION}) THEN 'REPORTADA_Y_VERIFICADA'
                         ELSE 'DISCREPANCIA_REVISAR' END""",
                           ('fecha_localizacion', 'fecha_desaparicion', 'dias_solucion'), 'control',
                           'Procedencia del intervalo; los casos sin localización no tienen duración completada.'),
                     Field('denuncia_anterior_desaparicion', 'c.fecha_denuncia < c.fecha_desaparicion',
                           ('fecha_denuncia', 'fecha_desaparicion'), 'control', 'Señal temporal; no elimina filas.'),
                 ) + provenance()),
    AnalyticView('v_defunciones', 'edg_limpia', 'Un registro de defunción conservado; no identifica personas únicas globalmente.',
                 'Contexto de mortalidad por tiempo, territorio, sexo, edad y causas reportadas.',
                 date_fields('fecha_fall', 'fecha_fallecimiento') + geography('prov_fall', 'cant_fall', codes=False) + (
                     direct('fecha_inscripcion', 'fecha_insc', role='control'), direct('sexo'),
                     Field('edad_valor', f"CASE WHEN c.edad_anios BETWEEN 0 AND 120 OR {EDG_INFANT} THEN c.edad END",
                           ('edad_anios', 'edad', 'cod_edad'), 'principal', 'Valor de edad con unidad; nunca promediar unidades mezcladas.'),
                     direct('edad_unidad', 'cod_edad'),
                     Field('edad_anios', 'CASE WHEN c.edad_anios BETWEEN 0 AND 120 THEN c.edad_anios END',
                           ('edad_anios',), 'principal', 'Años exactos; horas, días y meses no se rellenan con medias.'),
                     Field('grupo_edad', f"CASE WHEN {EDG_INFANT} THEN 'MENOR_DE_1_AÑO' ELSE {age_group('c.edad_anios')} END",
                           ('edad', 'cod_edad', 'edad_anios'), 'principal', 'Grupo derivado de la unidad conocida, sin asignar una edad exacta.'),
                     direct('edad_estado', role='control'), direct('cod_edad_estado', role='control'),
                     direct('causa'), direct('causa4', role='condicional', description='Agrupación de causa reportada; revisar su diccionario.'),
                     direct('circunstancia_externa_reportada', 'mor_viol', role='condicional',
                            missing='Campo de aplicación específica; NULL no significa muerte natural.'),
                     direct('mor_viol_estado', role='control'),
                     Field('autopsia_interpretada', "CASE WHEN c.autopsia IN ('SI','SÍ') THEN 'SI' WHEN c.autopsia='NO' THEN 'NO' END",
                           ('autopsia',), 'condicional', 'Solo respuestas explícitas sí/no; no adivina códigos numéricos.'),
                     direct('autopsia_estado', role='control'),
                     Field('autopsia_codigo_pendiente', "c.autopsia IS NOT NULL AND c.autopsia NOT IN ('SI','SÍ','NO')",
                           ('autopsia',), 'control', 'Respuesta presente que requiere diccionario antes de interpretarse.'),
                     direct('fecha_nac_posterior_fall', role='control'),
                 ) + provenance()),
    AnalyticView('v_enemdu', 'enemdu_limpia', 'Un registro de encuesta/ronda; no es una persona única entre meses.',
                 'Contexto socioeconómico con diseño muestral conservado; no es una estimación oficial automática.',
                 (
                     direct('periodo'), direct('periodo_estado', role='control'), direct('anio'), direct('mes', 'mes_periodo'),
                     Field('provincia', SURVEY_PROVINCE, ('provincia', 'codigo_provincia'), 'principal',
                           'Nombre observado o resuelto con código provincial único; no decide el cantón ambiguo.',
                           'Recuperación por catálogo único, no imputación estadística.'),
                     Field('provincia_origen', "CASE WHEN c.provincia IS NOT NULL THEN 'CLEAN' WHEN p.provincia IS NOT NULL THEN 'CATALOGO_PROVINCIAL_UNICO' ELSE 'PENDIENTE' END",
                           ('provincia', 'codigo_provincia'), 'control', 'Permite separar resolución geográfica y observación.'),
                     direct('canton'), direct('codigo_provincia', role='control'), direct('codigo_canton', role='control'),
                     direct('dpa_estado', role='control'),
                     Field('area', "CASE WHEN c.area='URBANA' THEN 'URBANO' ELSE c.area END", ('area',), 'principal', 'Área urbana/rural normalizada.'),
                 ) + demographics('p02', 'p03_estado', open_age=True) + (
                     direct('edad_censurada', role='control'), direct('edad_limite_inferior', role='control', description='Límite de edad, no edad exacta para calcular medias.'),
                     direct('nivel_instruccion', 'p10a', role='condicional', description='Etiquetas de educación; no asumir orden numérico sin diccionario.'),
                     direct('educacion_estado', 'p10a_estado', role='control'),
                     direct('ingreso_per_capita', 'ingpc'), direct('ingpc_estado', role='control'),
                     direct('ingreso_laboral', 'ingrl', role='condicional'), direct('ingrl_estado', role='control'),
                     direct('pobreza'), direct('pobreza_estado', role='control'), direct('pobreza_extrema', 'epobreza', role='condicional'),
                     Field('pobreza_binaria', "CASE WHEN c.pobreza='POBRE' THEN 1 WHEN c.pobreza='NO POBRE' THEN 0 END", ('pobreza',),
                           'principal', 'Indicador solo para categorías conocidas; NULL permanece fuera del denominador válido.'),
                     direct('condicion_actividad', 'condact', role='condicional', description='Clasificación reportada; homologación entre rondas pendiente.'),
                     direct('sector_empleo', 'secemp', role='condicional', missing='Evaluar dentro de su universo laboral; no imputar a toda la población.'),
                     direct('rama_actividad', 'rama1', role='condicional', description='Rama reportada; etiquetas con daños de codificación requieren revisión.'),
                     direct('factor_expansion', 'fexp', role='diseno_muestral'),
                     direct('estrato', role='diseno_muestral'), direct('upm', role='diseno_muestral'),
                     Field('apto_contexto_provincia_periodo', f"COALESCE(c.periodo IS NOT NULL AND {SURVEY_PROVINCE} IN ({sql_list(PROVINCES)}) AND c.fexp>0,FALSE)",
                           ('periodo', 'provincia', 'codigo_provincia', 'fexp'), 'control',
                           'Disponibilidad mínima para explorar contexto; no garantiza representatividad ni comparabilidad.'),
                 ) + provenance(False),
                 f'LEFT JOIN {SCHEMA}.v_catalogo_provincias p ON c.codigo_provincia=p.codigo_provincia'),
)


def catalog_sql():
    province = canonical_province('nombre_provincia')
    return f"""SELECT left(btrim(codigo_canton::text),2) AS codigo_provincia,
        min({province}) AS provincia
        FROM catalogo.dpa_ecuador
        WHERE btrim(codigo_canton::text) ~ '^[0-9]{{4}}$'
        GROUP BY left(btrim(codigo_canton::text),2)
        HAVING count(DISTINCT {province})=1
           AND min({province}) IN ({sql_list(PROVINCES)})"""


def definitions():
    result = {'v_catalogo_provincias': catalog_sql()}
    result.update({view.name: view.sql for view in VIEWS})
    return result
