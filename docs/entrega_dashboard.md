# Entrega de la primera versión del dashboard

## Aplicación

La interfaz está implementada en Vue 3, Vue Router, Vite, Tailwind y ECharts.
Se puede servir compilada con FastAPI, sin Power BI ni servidor Node en ejecución.

URL local de entrega: <http://127.0.0.1:8080>.
Documentación de API en ese modo: <http://127.0.0.1:8080/docs>.

Incluye:

- Resumen ejecutivo centrado en homicidios y contexto territorial.
- Páginas de homicidios, contexto, armas, desapariciones y defunciones.
- Líneas anuales/mensuales y comparación de hasta cuatro provincias.
- Matriz de calor provincia–año/mes, con clic para explorar.
- Dona por sexo con desconocidos visibles y porcentajes pequeños sin redondear a cero.
- Texto de interpretación calculado con la selección.
- Tablas, CSV con alcance/versión y PNG con título, período y referencia de carga.
- Evaluación temporal separada de las proyecciones experimentales.
- Metodología y cobertura de cada fuente.
- Diseño móvil con navegación lateral desplegable.

La portada utiliza **2018–2024** por defecto: muestra **26.249 registros**.
El total de toda la fuente es **38.931** al seleccionar 2014–2025; 2025 se marca
parcial (11 meses observados). No es un cambio de conteos por parte del gráfico.

La matriz temporal está operativa. El mapa geográfico es opcional y requiere
cartografía provincial verificada; su pestaña informa esta condición sin inventar geometrías.

## DW actualizado

Se cargó el nuevo mart `dwh.web_*` con dimensiones de tiempo/territorio, hechos
de seguridad y contexto, metadatos de carga y puntero activo.

| Fuente | Total de registros conservados |
|---|---:|
| Homicidios | 38.931 |
| Armas | 69.688 |
| Desapariciones | 75.461 |
| Defunciones | 717.297 |
| ENEMDU | 1.750.008 |

Los hechos y cubos históricos anteriores se conservaron; la aplicación nueva
consulta el mart web. Los totales se validaron contra las vistas analíticas y
las respuestas filtradas contra SQL.

## Viabilidad para nuevas cargas

- Publicación atómica: el dashboard utiliza la carga anterior mientras se construye la siguiente.
- Conservación de las dos últimas cargas completas del mart.
- Reenlace de vistas analíticas dentro de la transacción de publicación clean.
- Archivo del raw anterior, carga raw aparte y procedencia de archivos con SHA-256.
- Estados de calidad y cantidades no informadas conservados.
- Evaluación predictiva marcada desactualizada si cambia la versión de clean.

Comandos de trabajo desde la raíz:

```powershell
# Con raw ya preparado: validar, limpiar y actualizar el mart
python -m scripts.update_dashboard --from-raw

# Si clean ya está publicado: actualizar solo el mart
python -m scripts.update_dashboard

# Levantar la aplicación compilada
python -m scripts.serve_dashboard --production
```

La nueva carga debe utilizar formatos y reglas revisados; no se inventan
equivalencias para códigos nuevos. Las estimaciones ENEMDU y los modelos siguen
con sus limitaciones metodológicas visibles en el informe.

## Comprobaciones ejecutadas

- 46 pruebas Python con integración PostgreSQL: correctas.
- Verificación de actualización repetida y conservación de la carga anterior.
- Fallo simulado de refresco: el puntero activo se mantuvo.
- Reenlace de vistas e intercambio raw ensayados dentro de transacciones revertidas.
- Cinco pruebas unitarias de presentación/exportación en Node: correctas.
- Cinco pruebas de navegador sobre versión compilada: correctas.
- Navegación directa a páginas internas y `/health`/`/api/v1/meta`: HTTP 200.
- Compilación de producción: correcta.

Las capturas de escritorio y móvil están en `reports/dashboard/`.
Guía completa: [dashboard y actualización](dashboard_web.md).
