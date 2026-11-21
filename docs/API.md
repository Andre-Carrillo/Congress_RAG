# API HTTP de Congress_RAG

La API expone el mismo motor que la interfaz Streamlit: consultas SQL
deterministas, recuperación textual y la cadena RAG completa. La recuperación
funciona sin LLM; el modelo, si se activa, solo reformula la respuesta base.
Las cifras nunca las calcula el LLM y toda respuesta incluye acta, página y
enlace al PDF cuando corresponde.

## Arranque

```bash
uv run python scripts/ingest.py      # crea data/processed/congress.db
uv run python -m congress_rag.api    # http://127.0.0.1:8000
```

Opciones:

```bash
uv run python -m congress_rag.api --host 0.0.0.0 --port 8080
uv run python -m congress_rag.api --reload     # desarrollo
uv run uvicorn congress_rag.api.app:app --workers 4
make api
```

Documentación interactiva generada por FastAPI:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## Endpoints

### Estado

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio, base lista y conteos del corpus |
| GET | `/` | Nombre, versión y enlaces a documentación |

### Catálogo

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/legislaturas` | Legislaturas con actas y votaciones |
| GET | `/v1/tipos` | Tipos de votación detectados |
| GET | `/v1/bancadas` | Bancadas y cantidad de congresistas |
| GET | `/v1/actas` | Actas con páginas, PDF y cantidad de votaciones |

### Votaciones

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/votaciones` | Lista paginada; filtros `legislatura`, `tipo`, `acta_id`, `texto` |
| GET | `/v1/votaciones/{votacion_id}` | Detalle, conteos, acta y página |
| GET | `/v1/votaciones/{votacion_id}/bancadas` | Conteo por bancada |
| GET | `/v1/votaciones/{votacion_id}/votos` | Lista nominal según `posicion` |

`posicion` acepta `a_favor`, `en_contra`, `abstencion` y `no_voto`.
`no_voto` se deriva por complemento (congresistas activos sin voto explícito).

### Congresistas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/congresistas` | Padrón; filtro `buscar` por nombre |
| GET | `/v1/congresistas/{nombre}/historial` | Historial de voto, más reciente primero |

### Búsqueda textual

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/buscar` | Pasajes literales por similitud; no usa LLM |

Parámetros:

| Parámetro | Default | Uso |
|---|---|---|
| `q` | — | Texto a buscar (3–500 caracteres) |
| `tipo` | `narrativa` | Colección: `narrativa` (prosa del acta) o `votaciones` |
| `acta_id` | — | Acota a un acta, p. ej. `2026-06-03-10` |
| `legislatura` | — | Acota a `2025-2026-L1` o `2025-2026-L2` |
| `limit` | `5` | Cantidad de pasajes (1–20) |
| `min_score` | umbral de la colección | Similitud mínima (0–1) |

Este endpoint es la recuperación pura: sirve para comprobar que el texto de las
actas se puede consultar sin ningún proveedor de lenguaje.

### Consulta RAG

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/v1/consulta` | Pregunta en lenguaje natural |
| POST | `/v1/consulta/export` | Misma respuesta como Excel o Word |

Cuerpo de la petición:

```json
{
  "pregunta": "¿Cómo votó cada bancada en la moción 19785?",
  "usar_llm": false
}
```

`usar_llm=false` devuelve la respuesta base extractiva: tabla SQL y/o pasajes
literales de las actas con `[Acta ..., pág. ...]`. Con `true`, el LLM reformula
esa misma evidencia; si no está disponible o su texto no pasa la validación
(cifras o citas inventadas, fuentes omitidas), la API devuelve la base y lo
declara en `advertencias`. El campo `modo` indica `extractivo` o `redactado`.

### Calidad

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/calidad/resumen` | Conteos, confianza de votos y estado del QA |
| GET | `/v1/calidad/qa` | Filas del `qa_report.csv`; filtro `estado` |

## Ejemplos

```bash
# Estado
curl -s http://127.0.0.1:8000/health

# Buscar votaciones de la segunda legislatura
curl -s "http://127.0.0.1:8000/v1/votaciones?legislatura=2025-2026-L2&limit=5"

# Buscar por título
curl -s "http://127.0.0.1:8000/v1/votaciones?texto=moci%C3%B3n%2019785"

# Lista nominal en contra
curl -s "http://127.0.0.1:8000/v1/votaciones/2025-10-10-20-v002/votos?posicion=en_contra"

# Pregunta en lenguaje natural
curl -s -X POST http://127.0.0.1:8000/v1/consulta \
  -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Cómo votó cada bancada en la moción 19785?","usar_llm":false}'

# Recuperación textual sin LLM
curl -s "http://127.0.0.1:8000/v1/buscar?q=reforma%20del%20transporte&tipo=narrativa&limit=3"

# Exportar la respuesta a Excel
curl -s -X POST "http://127.0.0.1:8000/v1/consulta/export?formato=excel" \
  -H 'Content-Type: application/json' \
  -d '{"pregunta":"moción 19785","usar_llm":false}' \
  -o consulta.xlsx
```

Respuesta de `/v1/consulta`:

```json
{
  "pregunta": "¿Cómo votó cada bancada en la moción 19785?",
  "respuesta": "Votación: ... Acta 2025-10-10-20 · Página 7 ...",
  "fuentes": [
    {
      "acta_id": "2025-10-10-20",
      "pagina": 7,
      "pdf_url": "https://www2.congreso.gob.pe/...",
      "votacion_id": "2025-10-10-20-v002"
    }
  ],
  "tabla": {
    "titulo": "Conteo por bancada · 2025-10-10-20-v002",
    "columnas": ["Bancada", "A favor", "En contra", "Abstención", "Total"],
    "filas": [["Renovación Popular", 7, 0, 0, 7]],
    "metadata": {"votacion_id": "2025-10-10-20-v002"}
  },
  "fragmentos": [],
  "confianza": "alta",
  "modo": "extractivo",
  "advertencias": []
}
```

Respuesta de `/v1/buscar`:

```json
{
  "consulta": "reforma del transporte",
  "coleccion": "narrativa",
  "total": 1,
  "resultados": [
    {
      "acta_id": "2025-12-03-29",
      "pagina": 126,
      "score": 0.839,
      "texto": "…sustentó el dictamen y solicitó el apoyo…",
      "votacion_id": null,
      "pdf_url": "https://www2.congreso.gob.pe/..."
    }
  ],
  "advertencias": []
}
```

## Códigos de estado

| Código | Cuándo |
|---|---|
| 200 | Respuesta correcta |
| 404 | Votación inexistente |
| 422 | Parámetros inválidos (p. ej. pregunta de menos de 3 caracteres) |
| 503 | Falta `congress.db`; el detalle indica ejecutar la ingesta |

## Configuración

Variables en `.env`:

| Variable | Default | Uso |
|---|---|---|
| `API_HOST` | `127.0.0.1` | Host de escucha |
| `API_PORT` | `8000` | Puerto |
| `API_CORS_ORIGINS` | `*` | Orígenes permitidos, separados por coma |

## Notas de despliegue

- La API es de solo lectura sobre SQLite; varios workers de uvicorn pueden
  compartir la misma base.
- El primer `/v1/consulta` con `usar_llm=true` puede tardar más si debe cargar
  el modelo de embeddings o contactar al proveedor.
- Sin ChromaDB o sin embeddings, `/v1/buscar` devuelve `total=0` con una
  advertencia, y `/v1/consulta` sigue respondiendo desde SQL.
- Para exponerla fuera de la máquina, cambia `API_HOST` y restringe
  `API_CORS_ORIGINS` a los dominios reales.
