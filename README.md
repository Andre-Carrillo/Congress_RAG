# Congress_RAG

Sistema RAG híbrido para procesar y consultar actas de votación del Congreso del Perú.

## Qué resuelve

- Extrae votaciones de actas en PDF no tabulares.
- Responde preguntas en lenguaje natural con cifras exactas y citas (acta + página).
- Exporta tablas a Excel y Word sin desalinear filas ni columnas.
- Declara explícitamente cuando no hay evidencia en el corpus.

## Arquitectura

El sistema separa dos capas:

1. **Estructurada (SQLite):** votos, congresistas, bancadas y conteos exactos.
2. **Semántica (ChromaDB):** fragmentos de las actas para preguntas de contexto.

Un router decide qué capa usar. El LLM redacta la respuesta, pero **nunca calcula** los números.

## Alcance inicial

Dos últimas legislaturas ordinarias:

- `2025-2026-L1`
- `2025-2026-L2`

| Métrica | Valor |
|---|---|
| Actas | 41 |
| Votaciones | 676 |
| Filas de voto | 62,537 |
| Congresistas con voto registrado | 132 |
| Bancadas | 14 |

La fuente de datos es el proyecto `ushnu-congreso`, que ya contiene las actas extraídas a texto y las votaciones consolidadas. **No se ejecuta** el scraper ni el parser antiguo (evita ~5 horas de procesamiento).

## Datos incluidos

El repositorio incluye el corpus ya extraído para que puedas reconstruir la base sin volver a scrapear:

| Ruta | Contenido |
|---|---|
| `data/corpus/datos/publicos/` | sesiones, votaciones, votos consolidados, congresistas y bancadas del alcance |
| `data/corpus/datos/procesados/texto/` | 41 actas de las dos legislaturas, con marcadores de página |
| `data/corpus/legacy/votos_csv/` | votaciones del pipeline anterior, usadas para el contraste de calidad |
| `data/corpus/manifest.json` | origen, alcance, conteos y fecha de preparación |
| `data/processed/qa_report.csv` | reporte de calidad de las 676 votaciones |
| `data/processed/eval_resultados.csv` | resultados del set de evaluación sin LLM |

La base `data/processed/congress.db` y los `2,499` chunks de `data/processed/chunks.jsonl` se generan localmente con la ingesta y no se versionan por tamaño (17 MB + 11 MB).

Para regenerar el corpus incluido desde el proyecto completo:

```bash
uv run python scripts/prepare_corpus.py \
  --origen ~/Documents/dev/ushnu-congreso
```

Para reconstruir la base y los chunks desde ese corpus:

```bash
uv run python scripts/ingest.py
```

Si prefieres usar el corpus completo en lugar del incluido, ajusta `USHNU_DIR` y `LEGACY_DIR` en `.env` (ver `.env.example`).

## Instalación

```bash
cd ~/Documents/dev/Congress_RAG
cp .env.example .env
uv sync                 # dependencias base
uv sync --extra all     # embeddings + Chroma + LLM + Streamlit
```

## Uso

```bash
# 1. Ingesta: CSV de ushnu -> SQLite + chunks.jsonl + qa_report.csv
uv run python scripts/ingest.py

# 2. Índice vectorial (requiere extras de embeddings y Chroma)
uv run python scripts/build_index.py

# 3. Interfaz
uv run streamlit run src/congress_rag/ui/app.py

# 4. Tests
uv run pytest
```

## API HTTP

La API expone el mismo motor que la interfaz: SQL determinista, recuperación
semántica opcional y la cadena RAG completa.

```bash
uv run python scripts/ingest.py      # crea la base
uv run python -m congress_rag.api    # http://127.0.0.1:8000
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio y conteos del corpus |
| GET | `/v1/legislaturas`, `/v1/tipos`, `/v1/bancadas`, `/v1/actas` | Catálogo |
| GET | `/v1/votaciones` | Lista paginada con filtros |
| GET | `/v1/votaciones/{id}` | Detalle de una votación |
| GET | `/v1/votaciones/{id}/bancadas` | Conteo por bancada |
| GET | `/v1/votaciones/{id}/votos?posicion=` | Votos a favor, en contra, abstención o no voto |
| GET | `/v1/congresistas` | Padrón filtrable por nombre |
| GET | `/v1/congresistas/{nombre}/historial` | Historial de voto |
| POST | `/v1/consulta` | Pregunta en lenguaje natural |
| POST | `/v1/consulta/export?formato=excel\|word` | Exportación reproducible |
| GET | `/v1/calidad/resumen`, `/v1/calidad/qa` | Transparencia del corpus |

```bash
curl -s -X POST http://127.0.0.1:8000/v1/consulta \
  -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Cómo votó cada bancada en la moción 19785?","usar_llm":false}'
```

Documentación completa y ejemplos: [`docs/API.md`](docs/API.md).

## Estructura

```
src/congress_rag/
├── config.py          # configuración por .env
├── schemas.py         # modelos de dominio
├── db/                # SQLAlchemy + SQLite
├── ingestion/         # bootstrap, normalización, parser, chunker
├── indexing/          # embeddings y ChromaDB
├── rag/               # router, SQL tools, LLM, cadena
├── export/            # Excel y Word
├── api/               # FastAPI: endpoints HTTP
└── ui/                # Streamlit
```

## Estado

- [x] Arquitectura y modelo de datos
- [x] Ingesta estructurada desde `ushnu-congreso`
- [x] Reporte de calidad (`qa_report.csv`): 659/676 con integridad verificada
- [x] Chunker por votación y narrativo (2,499 chunks)
- [ ] Índice vectorial poblado (requiere extras de embeddings y Chroma)
- [x] Router + cadena RAG determinista con citas
- [x] UI Streamlit y exportación a Excel/Word
- [x] API HTTP con FastAPI (Swagger en `/docs`) y exportación por endpoint
- [x] Set dorado de evaluación inicial
- [x] 50 tests unitarios

## Documentación

- `docs/API.md`
- `docs/PLAN_Congress_RAG.md`
- `docs/ARQUITECTURA_PRESENTACION_Congress_RAG.md`
