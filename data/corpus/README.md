# Corpus incluido

Este directorio contiene el subconjunto del corpus público del Congreso del
Perú usado por `Congress_RAG` para las legislaturas `2025-2026-L1` y
`2025-2026-L2`.

Los archivos provienen del proyecto [ushnu-congreso](https://github.com/Andre-Carrillo/ushnu-congreso),
que ya realizó la descarga y el procesamiento de las actas. **No se ejecutó un
scraper nuevo para generar este repositorio**: se copiaron y filtraron los
artefactos ya extraídos para que el proyecto sea reproducible sin una corrida
de ~5 horas.

## Contenido

- `datos/publicos/sesiones.csv`: 41 sesiones del alcance.
- `datos/publicos/votaciones.csv`: 676 votaciones con posición y página.
- `datos/publicos/votos_largo_consolidado.csv`: 62,537 filas de voto.
- `datos/publicos/congresistas_oficiales_actuales.csv`: padrón oficial.
- `datos/publicos/bancadas_resueltas_general.csv`: bancadas resueltas.
- `datos/publicos/registro_extraccion.csv`: URL y hash del PDF de cada acta.
- `datos/procesados/texto/`: las 41 actas en texto, con marcadores de página.
- `legacy/votos_csv/`: matrices del pipeline anterior, usadas para el contraste de calidad.
- `manifest.json`: conteos y fecha de preparación.

## Regeneración

```bash
uv run python scripts/prepare_corpus.py --origen ~/Documents/dev/ushnu-congreso
```
