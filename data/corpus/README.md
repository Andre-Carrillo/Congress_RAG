# Corpus incluido

Este directorio contiene el corpus de actas y votaciones del Congreso del Perú
usado por `Congress_RAG` para las legislaturas `2025-2026-L1` y `2025-2026-L2`
(periodo anual 2025-2026).

Las actas ya están descargadas y extraídas a texto, y las votaciones están
consolidadas. Por eso el repositorio funciona sin ejecutar un scraper ni un
parser de PDF: la ingesta solo carga estos archivos en SQLite.

## Contenido

- `publicos/sesiones.csv`: 41 sesiones del alcance.
- `publicos/votaciones.csv`: 676 votaciones con posición y página.
- `publicos/votos_largo_consolidado.csv`: 62,537 filas de voto.
- `publicos/congresistas_oficiales_actuales.csv`: padrón oficial.
- `publicos/bancadas_resueltas_general.csv`: bancadas resueltas.
- `publicos/registro_extraccion.csv`: URL y hash del PDF de cada acta.
- `actas/`: las 41 actas en texto, con marcadores de página.
- `legacy/votos_csv/`: matrices del pipeline anterior, usadas para el contraste de calidad.
- `manifest.json`: alcance, conteos y fecha de preparación.

## Regeneración

```bash
uv run python scripts/ingest.py
```

Ese comando reconstruye `data/processed/congress.db`, `chunks.jsonl` y
`qa_report.csv` a partir de este corpus.
