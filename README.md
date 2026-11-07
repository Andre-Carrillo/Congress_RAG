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
- [x] Set dorado de evaluación inicial
- [x] 34 tests unitarios

## Documentación

- `docs/PLAN_Congress_RAG.md`
- `docs/ARQUITECTURA_PRESENTACION_Congress_RAG.md`
