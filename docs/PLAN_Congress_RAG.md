# Plan del Proyecto — Congress_RAG
## Sistema RAG híbrido para procesamiento y consulta de actas de votación del Congreso

**Versión:** 1.0
**Fecha:** 7 de noviembre de 2026
**Autor:** André Carrillo
**Proyecto base:** `~/Documents/dev/Congress_Analysis`
**Fuente de datos principal:** `~/Documents/dev/ushnu-congreso`

---

## 1. Planteamiento del problema

Las actas de votación que publica el Congreso en PDF presentan tres problemas concretos:

1. **Estructura no tabular.** Los registros de votación son listas de texto con espaciado irregular producido por el OCR (`MOCI ÓN`, `CONG RESISTAS`). No son tablas reales, por lo que `pdfplumber` no las detecta como tales.
2. **Pérdida de alineación al exportar.** Al convertir a Word o Excel, las columnas de nombres y posiciones de voto se desalinean, obligando a reconstruir la tabla manualmente.
3. **Costo de fiscalización.** Responder "¿cómo votó cada bancada en la moción X?" requiere revisar decenas de páginas por acta. En el alcance de este prototipo son **4,619 páginas** de texto.

El proyecto anterior (`Congress_Analysis`) resolvió parcialmente el problema 1 con un parser de expresiones regulares y produjo matrices de voto en CSV. Sin embargo, ese pipeline:

- tarda aproximadamente **5 horas** en reprocesar el corpus completo,
- pierde la referencia de página, por lo que no permite citar la fuente,
- no tiene validación automática contra los conteos declarados en el propio PDF,
- no responde preguntas en lenguaje natural.

## 2. Hipótesis

Es posible construir un asistente que responda consultas en lenguaje natural sobre las votaciones, con cifras exactas y fuentes verificables, combinando:

- una **capa estructurada** (SQLite) para conteos y agregaciones deterministas,
- una **capa semántica** (ChromaDB) para recuperar contexto narrativo del acta,
- un **LLM local cuantizado** que redacta la respuesta pero **no calcula** los números.

El resultado debe permitir exportar tablas exactas a Excel y Word sin desorganizar los datos, y debe rechazar explícitamente las preguntas que no tengan respaldo en el corpus.

## 3. Alcance del prototipo

### Decisión de alcance

Para la presentación de avance y la primera versión funcional se usan **las dos últimas legislaturas ordinarias**:

- `2025-2026-L1` — Primera Legislatura Ordinaria del Periodo Anual 2025-2026
- `2025-2026-L2` — Segunda Legislatura Ordinaria del Periodo Anual 2025-2026

### Decisión de proceso: no ejecutar `scrap.py` ni `pdf_to_csv.py`

El proyecto `ushnu-congreso` ya contiene:

- las **265 actas extraídas a texto** con marcadores de página (`===== PAGINA N =====`),
- **4,334 votaciones** parseadas con posición y página de inicio,
- **433,832 filas de voto** consolidadas con nivel de confianza y trazabilidad de subsanaciones,
- las **URLs de los PDF originales** para cada acta.

Por lo tanto, **no se ejecutará el scraper ni el parser antiguo** para construir el prototipo. Esto elimina las ~5 horas de procesamiento y mejora la calidad de los datos de entrada (página, confianza, subsanaciones).

El proyecto `Congress_Analysis` se conserva como **fuente de validación cruzada**: sus CSV `5.1` y `5.2` permiten medir cuántas votaciones recupera el pipeline nuevo.

### Métricas exactas del alcance

| Métrica | Valor |
|---|---|
| Actas | **41** (29 en L1 + 12 en L2) |
| Votaciones | **676** (402 en L1 + 274 en L2) |
| Filas de voto | **62,537** (37,483 en L1 + 25,054 en L2) |
| Congresistas con voto registrado | **132** |
| Bancadas en el registro oficial | **14** |
| Páginas de texto del acta | **4,619** |
| Caracteres de texto | **8.69 M** (~2.17 M tokens) |
| Distribución de votos | Sí 54,064 · No 5,642 · Abstención 2,831 |
| Confianza del parseo | Alta 5,974 · Media 56,563 |
| Fuente del voto | Registro digital 56,289 · Subsanación 6,237 · Cambio de subsanación 11 |

### Hallazgo que justifica el reproceso

| Legislatura | Votaciones en `Congress_Analysis` | Votaciones en `ushnu-congreso` | Diferencia |
|---|---|---|---|
| 2025-2026-L1 | 402 (`votos_csv/5.1.csv`) | 402 | 0 |
| 2025-2026-L2 | 226 (`votos_csv/5.2.csv`) | 274 | **+48 recuperadas (+21%)** |

Los datos consolidados de `ushnu-congreso` contienen 48 votaciones más que el CSV del pipeline anterior. Es evidencia medible de que el CSV legacy está incompleto, no una opinión.

## 4. Fuentes de datos

Todas las rutas son relativas a `~/Documents/dev/ushnu-congreso`.

| Archivo | Contenido | Uso en el proyecto |
|---|---|---|
| `datos/procesados/texto/*.txt` | 265 actas con marcadores de página | Corpus narrativo y reconstrucción del bloque de votación |
| `datos/publicos/sesiones.csv` | `acta_id`, fecha, periodo, `legislatura_codigo` | Filtro de alcance y metadata |
| `datos/publicos/votaciones.csv` | 4,334 votaciones con `pagina_inicio`, `posicion_inicio/fin`, conteos | Tabla `votaciones` y validación |
| `datos/publicos/votos_largo_consolidado.csv` | 433,832 filas con `voto_normalizado`, `confianza`, `fuente_voto` | Tabla `votos` y validación |
| `datos/publicos/congresistas_oficiales_actuales.csv` | 140 congresistas, grupo parlamentario | Tabla `congresistas` |
| `datos/publicos/bancadas_resueltas_general.csv` | Bancada por congresista y fecha | Metadata de bancada |
| `datos/publicos/registro_extraccion.csv` | `pdf_url` y SHA-256 por acta | Enlace "ver PDF" en las citas |
| `datos/publicos/votaciones_clasificadas.csv` | Categorías detectadas por votación | Filtro por tipo |

Fuente de validación cruzada: `~/Documents/dev/Congress_Analysis/votos_csv/5.1.csv` y `5.2.csv`.

## 5. Decisión arquitectónica: RAG híbrido, no RAG puro

### Por qué un RAG puro no alcanza

Un RAG vectorial devuelve los *k* fragmentos más similares. Eso funciona para "¿qué se debatió sobre la moción X?", pero falla en:

- **"¿Cómo votó cada bancada en la moción X?"** → requiere agregación exacta de todos los votos, no un top-k.
- **"Genera una lista ordenada de las abstenciones"** → requiere completitud, no similitud.
- **"¿Cuántos votos a favor hubo?"** → el LLM no debe contar; debe leer el total de la base.

Si se le pide al LLM agregar sobre cinco fragmentos recuperados, inventará totales. Es el modo de fallo más común de los RAG aplicados a datos tabulares.

### Solución: router + dos capas

| Intención de la consulta | Capa que responde | Ejemplo |
|---|---|---|
| Agregación / conteo | **SQL determinista** | "¿Cuántos votaron a favor por bancada?" |
| Búsqueda de contenido | **Vectorial + narrativa** | "¿Qué argumentos se dieron en el debate?" |
| Mixta | **Ambas, con merge** | "Resume el debate y muestra cómo votó cada bancada" |

El LLM solo redacta y estructura. Los números salen de SQLite. Las citas salen de la metadata del chunk.

## 6. Arquitectura general

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FUENTES DE DATOS                              │
│  ushnu-congreso: texto de actas + votaciones.csv + votos_largo.csv    │
│  Congress_Analysis: votos_csv/5.1.csv, 5.2.csv (validación cruzada)   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      INGESTA (offline, idempotente)                   │
│                                                                       │
│  extractor.py ──▶ parser.py ──▶ name_resolver.py ──▶ SQLite           │
│  (texto por página)  (votaciones)   (132 congresistas)   congress.db  │
│                                                                       │
│  chunker.py ──▶ chunks.jsonl ──▶ embeddings.py ──▶ ChromaDB           │
│  (1 chunk por votación)          (e5-small)          data/chroma/     │
│                                                                       │
│  qa_report.csv  ◀── validación contra conteos declarados y legacy     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        CONSULTA (online, Streamlit)                   │
│                                                                       │
│  Pregunta ──▶ router.py ──▶ ┌──────────────┐                          │
│  (español)   (QueryPlan)     │ sql_tools.py │──▶ SQLite (exacto)       │
│                              │ retriever.py │──▶ Chroma (semántico)    │
│                              └──────┬───────┘                          │
│                                     ▼                                  │
│                              chain.py + llm.py                         │
│                              (Ollama / Gemini)                         │
│                                     ▼                                  │
│                         Respuesta + citas + TableSpec                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  EXPORTACIÓN                 UI                                       │
│  excel.py (openpyxl)         Streamlit: Ingesta · Consulta ·          │
│  word.py  (python-docx)      Explorador · Calidad                     │
└──────────────────────────────────────────────────────────────────────┘
```

## 7. Estructura del repositorio

```
Congress_RAG/
├── pyproject.toml
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── data/
│   ├── raw/                      # enlaces o copia de PDFs (opcional)
│   ├── processed/
│   │   ├── congress.db           # SQLite
│   │   ├── chunks.jsonl
│   │   └── qa_report.csv
│   └── chroma/                   # índice persistente
├── src/congress_rag/
│   ├── config.py
│   ├── schemas.py
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   ├── ingestion/
│   │   ├── extractor.py
│   │   ├── normalize.py
│   │   ├── parser.py
│   │   ├── name_resolver.py
│   │   ├── bootstrap_legacy.py
│   │   └── pipeline.py
│   ├── indexing/
│   │   ├── chunker.py
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   └── build_index.py
│   ├── rag/
│   │   ├── router.py
│   │   ├── retriever.py
│   │   ├── sql_tools.py
│   │   ├── prompts.py
│   │   ├── llm.py
│   │   └── chain.py
│   ├── export/
│   │   ├── excel.py
│   │   └── word.py
│   └── ui/
│       ├── app.py
│       └── pages/
│           ├── 1_Ingesta.py
│           ├── 2_Consulta.py
│           ├── 3_Explorador.py
│           └── 4_Calidad.py
├── scripts/
│   ├── ingest.py
│   ├── build_index.py
│   └── evaluate.py
└── tests/
    ├── fixtures/
    ├── test_normalize.py
    ├── test_parser.py
    ├── test_name_resolver.py
    ├── test_chunker.py
    └── test_sql_tools.py
```

## 8. Modelo de datos (SQLite)

```sql
CREATE TABLE congresistas (
    id                  INTEGER PRIMARY KEY,
    congresista_id      TEXT UNIQUE,        -- id oficial de ushnu
    nombre              TEXT NOT NULL,
    nombre_normalizado  TEXT NOT NULL,
    grupo_partido       TEXT,
    bancada             TEXT,
    perfil_url          TEXT
);

CREATE TABLE legislaturas (
    id                  TEXT PRIMARY KEY,   -- "2025-2026-L1"
    periodo_anual       TEXT,               -- "2025-2026"
    nombre              TEXT                -- "PRIMERA LEGISLATURA ORDINARIA"
);

CREATE TABLE documentos (
    id                  INTEGER PRIMARY KEY,
    acta_id             TEXT UNIQUE,        -- "2026-03-05-01"
    numero_sesion       INTEGER,
    fecha               TEXT,
    legislatura_id      TEXT REFERENCES legislaturas(id),
    ruta_texto          TEXT,
    pdf_url             TEXT,
    n_paginas           INTEGER,
    hash_sha256         TEXT
);

CREATE TABLE votaciones (
    id                  INTEGER PRIMARY KEY,
    votacion_id         TEXT UNIQUE,        -- "2026-03-05-01-v003"
    documento_id        INTEGER REFERENCES documentos(id),
    indice_votacion     INTEGER,
    pagina_inicio       INTEGER,
    titulo              TEXT NOT NULL,
    titulo_normalizado  TEXT NOT NULL,
    tipo                TEXT,               -- moción, proyecto, cuestión previa...
    conteo_si           INTEGER,
    conteo_no           INTEGER,
    conteo_abstencion   INTEGER,
    conteo_listado      INTEGER,
    origen              TEXT                -- "ushnu" | "legacy" | "pdf"
);

CREATE TABLE votos (
    votacion_id         INTEGER REFERENCES votaciones(id),
    congresista_id      INTEGER REFERENCES congresistas(id),
    posicion            INTEGER NOT NULL,   -- 1 sí, -1 no, 0 abstención, 2 no votó
    confianza           TEXT,               -- alta | media | baja
    fuente_voto         TEXT,               -- registro_digital | subsanacion
    PRIMARY KEY (votacion_id, congresista_id)
);

CREATE TABLE chunks (
    id                  TEXT PRIMARY KEY,
    documento_id        INTEGER REFERENCES documentos(id),
    votacion_id         INTEGER REFERENCES votaciones(id),  -- NULL para narrativa
    pagina              INTEGER,
    tipo                TEXT NOT NULL,      -- votacion | narrativa
    texto               TEXT NOT NULL,
    metadata_json       TEXT
);
```

Índices obligatorios: `votos(votacion_id)`, `votos(congresista_id)`, `votaciones(documento_id)`, `chunks(votacion_id)`.

**Nota sobre la confianza:** 56,563 de 62,537 filas tienen confianza `media`. La app debe mostrar un indicador de confianza por votación y permitir filtrar solo `alta` en el explorador. No se oculta la limitación: se expone.

## 9. Pipeline de ingesta

### 9.1 Bootstrap estructurado

`bootstrap_legacy.py` carga, para las dos legislaturas:

1. `sesiones.csv` filtrado por `legislatura_codigo IN ('2025-2026-L1','2025-2026-L2')` → `documentos`.
2. `votaciones.csv` filtrado por los `acta_id` anteriores → `votaciones`.
3. `votos_largo_consolidado.csv` filtrado por los `votacion_id` anteriores → `votos`.
4. `congresistas_oficiales_actuales.csv` + `bancadas_resueltas_general.csv` → `congresistas`.
5. `Congress_Analysis/votos_csv/5.1.csv` y `5.2.csv` → tabla temporal `votos_legacy` para comparación.

### 9.2 Extracción y normalización

`extractor.py` lee el `.txt` y separa por `===== PAGINA N =====`, produciendo `(n_pagina, texto)`.

`normalize.py` aplica:

- colapso de espaciado intra-palabra del OCR,
- normalización Unicode NFC y eliminación de acentos para comparación,
- limpieza de encabezados y pies (`DEPARTAMENTO DE RELATORÍA`, `- N -`, `S A R E A D E R E D A C C I Ó N D E A C T A S`).

**Estos módulos se implementan con tests primero**, usando 3 actas de fixture (una de L1, una de L2, una con subsanaciones).

### 9.3 Chunk por votación

El chunk se construye uniendo:

1. el bloque de texto exacto de la votación (`posicion_inicio` a `posicion_fin`),
2. las listas de voto reconstruidas desde `votos_largo_consolidado.csv`,
3. la distribución por bancada calculada por SQL.

Plantilla:

```
VOTACIÓN: {titulo}
Acta {acta_id} · Sesión Nº {n} · Página {pagina_inicio}
Legislatura {legislatura_id}
Resultado declarado: {si} a favor, {no} en contra, {abst} abstenciones

A FAVOR ({n}): ...
EN CONTRA ({n}): ...
ABSTENCIÓN ({n}): ...

DISTRIBUCIÓN POR BANCADA:
  Fuerza Popular: 12 a favor, 0 en contra, 0 abstenciones
  ...

EXTRACTO DEL DEBATE:
  {texto del bloque}
```

Un chunk por votación (676 chunks) + chunks narrativos de ~800 tokens con solape de 100 para el resto del acta.

### 9.4 Reporte de calidad

`qa_report.csv` con una fila por votación:

| columna | descripción |
|---|---|
| `votacion_id` | identificador |
| `conteo_si`, `conteo_no`, `conteo_abst` | declarados en el registro digital original |
| `extraido_si`, `extraido_no`, `extraido_abst` | calculados desde `votos` consolidados |
| `delta_*`, `recuperados` | diferencia atribuida a subsanaciones posteriores |
| `legacy_si`, `legacy_no`, `legacy_abst` | calculados desde `votos_csv` |
| `estado` | `ok`, `recuperado_subsanacion`, `ajuste_por_subsanacion`, `discrepancia_conteo`, `sin_votos` |
| `confianza_alta_pct` | proporción de filas con confianza `alta` |

Criterio: ≥95% de las 676 votaciones sin pérdida de votos respecto del registro
digital. El resultado de la primera corrida es **659/676 (97.5%)**, con
**+5,974 votos recuperados** por subsanaciones y 17 votaciones con
redistribución de posiciones para revisión.

## 10. Indexación vectorial

- **Modelo:** `intfloat/multilingual-e5-small` (118 MB), con prefijos `query:` y `passage:`.
- **Base:** ChromaDB persistente en `data/chroma/`.
- **Colecciones:**
  - `votaciones` — 676 chunks estructurados.
  - `narrativa` — fragmentos del debate.
- **Metadata por chunk:** `legislatura_id`, `acta_id`, `pagina`, `tipo`, `bancadas_mencionadas`, `anio`.
- **Búsqueda:** filtro por metadata + similitud coseno, `top_k=5` por defecto, umbral mínimo de score.

Justificación del modelo: `all-MiniLM-L6-v2` (el del planteamiento original) está entrenado en inglés y rinde peor en español. `multilingual-e5-small` mantiene un tamaño reducido y cubre castellano.

## 11. Capa RAG

### 11.1 QueryPlan

```python
class Filtros(BaseModel):
    legislatura: str | None = None
    bancada: str | None = None
    congresista: str | None = None
    acta_id: str | None = None
    tipo: str | None = None
    proyecto_o_mocion: str | None = None

class QueryPlan(BaseModel):
    intencion: Literal["agregacion", "busqueda", "mixta", "fuera_de_alcance"]
    filtros: Filtros
    requiere_sql: bool
    requiere_contexto: bool
    consulta_reescrita: str
```

### 11.2 Consultas SQL permitidas

`sql_tools.py` expone funciones parametrizadas, nunca SQL generado libremente:

1. `buscar_votacion(texto) -> list[Votacion]`
2. `conteo_por_bancada(votacion_id) -> list[ConteoBancada]`
3. `lista_votos(votacion_id, posicion) -> list[NombreVoto]`
4. `historial_congresista(congresista, filtros) -> list[VotoDetalle]`
5. `comparar_bancadas(votacion_id, bancada_a, bancada_b) -> Comparacion`
6. `ausencias_por_votacion(votacion_id) -> list[NombreVoto]`
7. `votaciones_por_tipo(tipo, legislatura) -> list[Votacion]`

Cada función devuelve un `TableSpec` (columnas + filas) que la UI puede renderizar y exportar.

### 11.3 Proveedores LLM

```python
class LLMProvider(Protocol):
    def generate(self, prompt: str, *, schema: type[BaseModel] | None = None) -> str | BaseModel: ...
    def name(self) -> str: ...

class OllamaProvider:   # qwen2.5:7b-instruct, format=schema
class GeminiProvider:   # google-genai, response_schema nativo
```

Selección por `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b-instruct
GEMINI_MODEL=gemini-2.0-flash
```

`qwen2.5:7b-instruct` se prefiere sobre Llama 3/Mistral por su mejor desempeño en español. La abstracción permite cambiar de backend sin tocar el resto del sistema.

### 11.4 Reglas anti-alucinación

1. El prompt incluye solo el contexto recuperado y los resultados SQL.
2. Toda afirmación numérica debe provenir de `sql_tools`; el LLM tiene prohibido calcular.
3. Cada respuesta incluye `fuentes: list[Fuente]` con `acta_id`, `pagina` y `pdf_url`.
4. Si no hay evidencia, la respuesta es exactamente: *"No se encontró evidencia en el corpus para responder esta consulta."*
5. Si la pregunta está fuera de las dos legislaturas cargadas, el sistema lo declara antes de responder.
6. La exportación se genera desde `TableSpec` → SQL, nunca desde texto libre del LLM.

## 12. Exportación

- **Excel** (`openpyxl`): hoja de resultados, formato condicional por voto (verde/rojo/gris), encabezados congelados, hoja de metadatos con `acta_id`, `votacion_id`, página y URL del PDF.
- **Word** (`python-docx`): pregunta original, respuesta, tabla, y sección de fuentes con enlaces.

Ambas exportaciones son reproducibles: los mismos filtros producen la misma tabla.

## 13. Interfaz Streamlit

| Página | Función |
|---|---|
| `1_Ingesta` | Ejecutar bootstrap, ver progreso, descargar `qa_report.csv` |
| `2_Consulta` | Chat con filtros (legislatura, bancada, tipo), fuentes expandibles, botones de exportación |
| `3_Explorador` | Tabla filtrable de votaciones, pivot congresista × votación, distribución por bancada |
| `4_Calidad` | Conteos inconsistentes, votaciones con confianza media/baja, cobertura por legislatura |

## 14. Evaluación

### Set dorado

30–50 preguntas con respuesta verificable, distribuidas en:

- 15 de agregación (conteos por bancada, listas de votos),
- 15 de búsqueda (contenido del debate, identificar una votación),
- 10 mixtas,
- 5 negativas (preguntas sin respuesta en el corpus, para medir rechazos correctos).

### Métricas

| Métrica | Objetivo |
|---|---|
| Retrieval hit rate @5 | ≥90% |
| Exactitud numérica en agregaciones | 100% (proviene de SQL) |
| Citas correctas (acta + página) | ≥95% |
| Rechazos correctos en preguntas negativas | ≥90% |
| Latencia de respuesta (Ollama local) | <15 s |

## 15. Fases y cronograma

| Fase | Entregable | Duración | Semana |
|---|---|---|---|
| 0. Setup | Repo, `pyproject.toml`, config, schemas | 0.5 día | Semana 1 |
| 1. Ingesta estructurada | `congress.db` + `qa_report.csv` con las 676 votaciones | 2–3 días | Semana 1 |
| 2. Chunking e índice | `chunks.jsonl` + Chroma poblado y consultable | 1–2 días | Semana 2 |
| 3. RAG | Router, SQL tools, cadena con citas | 2 días | Semana 2 |
| 4. UI | 4 páginas Streamlit funcionales | 2 días | Semana 3 |
| 5. Exportación | Excel y Word desde `TableSpec` | 1 día | Semana 3 |
| 6. Evaluación | Set dorado y reporte de métricas | 1–2 días | Semana 4 |

Total: **10–13 días efectivos**.

## 16. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Python 3.14/3.15 sin wheels de PyTorch | Alto | Fijar el proyecto nuevo a **Python 3.12** |
| Texto OCR con espaciado irregular | Alto | Capa `normalize.py` con tests sobre actas reales |
| 90% de votos con confianza `media` | Medio | Exponer confianza en UI; permitir filtro `alta`; validar contra conteos declarados |
| Nombres no resueltos o alias | Medio | Usar el `congresista_id` oficial de `ushnu-congreso`, que ya resolvió identidades |
| Subsanaciones que cambian un voto | Medio | Usar `voto_consolidado` y conservar `voto_original` y `subsanacion_id` para auditoría |
| Agregaciones inventadas por el LLM | Alto | SQL determinista obligatorio; el LLM no calcula |
| ChromaDB incompatible con el entorno | Bajo | Interfaz `vector_store.py` con alternativa FAISS |
| Respuestas lentas en CPU | Medio | `qwen2.5:7b` cuantizado; opción Gemini para demo; caché de consultas frecuentes |

## 17. Criterios de aceptación

El prototipo se considera listo cuando:

1. Carga las **41 actas** y las **676 votaciones** sin intervención manual.
2. `qa_report.csv` muestra ≥95% de votaciones en estado `ok`.
3. Responde correctamente las cuatro preguntas del planteamiento original:
   - ¿Cómo votó cada bancada en la moción X?
   - Genera una lista ordenada de las abstenciones.
   - ¿Qué congresistas votaron en contra del proyecto Y?
   - ¿Cuál fue el resultado de la votación Z?
4. Cada respuesta incluye acta y página verificables.
5. Exporta a Excel y Word sin desalinear filas ni columnas.
6. Rechaza correctamente las 5 preguntas negativas del set dorado.

## 18. Decisiones cerradas

| Tema | Decisión |
|---|---|
| Ubicación | Repo nuevo `~/Documents/dev/Congress_RAG` |
| Alcance | `2025-2026-L1` y `2025-2026-L2` |
| Fuente de datos | `ushnu-congreso` (texto + CSV consolidados) |
| Scraper / parser antiguo | **No se ejecutan** |
| LLM | Abstracción Ollama + Gemini |
| Embeddings | `intfloat/multilingual-e5-small` |
| Vector store | ChromaDB |
| DB estructurada | SQLite |
| UI | Streamlit |
| Python | 3.12 |

## 19. Pendientes de confirmar

1. Si "las dos últimas legislaturas" se refiere a `2025-2026-L1/L2` (asunción de este plan) o a `2024-2025-L2` + `2025-2026-L1`.
2. Si la presentación requiere un demo en vivo o solo la arquitectura y las métricas.
3. Si se desea incluir el enlace "ver PDF" en las citas (requiere conexión a internet durante la demo).
