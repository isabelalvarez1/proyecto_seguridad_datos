# Artefactos de modelos

Esta carpeta contiene salidas locales generadas por `ml/`. Los `.pkl` y `.png`
están excluidos de Git.

La API necesita estos seis archivos al arrancar:

```text
rf_homicidios.pkl
xgb_homicidios.pkl
mappings_homicidios.pkl
features_homicidios.pkl
rf_clasificador_riesgo.pkl
mappings_riesgo.pkl
```

Se generan desde la raíz del proyecto con:

```powershell
python -m ml.ml_homicidio
python -c "from ml.modelo_riesgo import modelo_riesgo; modelo_riesgo()"
```

Reentrenar modelo y mappings juntos cuando cambie el vocabulario geográfico.
Reiniciar la API para cargar los nuevos artefactos. Conservar las versiones de
dependencias utilizadas para reproducir y cargar cada experimento.
