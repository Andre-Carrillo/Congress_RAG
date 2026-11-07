# Congress_RAG — Arquitectura y avance
## Asistente para consultar actas de votación del Congreso en lenguaje natural

**Presentación de avance · 7 de noviembre de 2026**
**André Carrillo**

> **Una línea:** un asistente que responde preguntas sobre votaciones con cifras exactas, cita el acta y la página, y exporta la tabla a Excel o Word sin desalinearla.

---

## Slide 1 — El problema

| Dolor | Evidencia |
|---|---|
| Los PDF de actas no son tablas | Listas de texto con OCR irregular: `MOCI ÓN`, `CONG RESISTAS` |
| Exportar desorganiza los datos | Al pasar a Word/Excel, nombres y votos pierden alineación |
| Fiscalizar es manual | Responder una pregunta exige revisar decenas de páginas |

**En el alcance del prototipo:** 41 actas, 676 votaciones, 4,619 páginas.

**Lo que ya existe:** el proyecto `Congress_Analysis` extrae votos a CSV, pero tarda ~5 horas, no cita páginas y no responde preguntas.

---

## Slide 2 — La propuesta

**No es un RAG puro. Es un RAG híbrido.**

```
Pregunta ──▶ ¿Qué necesita?
                │
      ┌─────────┴─────────┐
      ▼                   ▼
  Números             Contexto
  SQLite              ChromaDB
  (exacto)            (semántico)
      └─────────┬─────────┘
                ▼
             LLM local
        (redacta, no calcula)
                ▼
      Respuesta + cita + tabla
```

| Tipo de pregunta | Capa |
|---|---|
| "¿Cómo votó cada bancada en la moción X?" | SQL |
| "¿Qué se debatió sobre la moción X?" | Vectorial |
| "Resume el debate y muestra la votación" | Ambas |

**Por qué:** un RAG vectorial devuelve los 5 fragmentos más parecidos, no todos los votos. Si el LLM agrega sobre un top-k, inventa totales.

---

## Slide 3 — Arquitectura

```
┌─────────────────────────────────────────────────────┐
│ FUENTES                                             │
│ ushnu-congreso: 265 actas en texto + 433k votos     │
│ Congress_Analysis: votos_csv 5.1 / 5.2 (validación) │
└───────────────────────┬─────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│ INGESTA (offline)                                   │
│ extractor → parser → resolver → SQLite (congress.db)│
│ chunker → e5-small → ChromaDB                       │
│ qa_report.csv: validación contra conteos del acta   │
└───────────────────────┬─────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│ CONSULTA (Streamlit)                                │
│ router → sql_tools (exacto)                         │
│        → retriever (semántico)                      │
│        → LLM (Ollama / Gemini)                      │
│        → respuesta + cita + TableSpec               │
└───────────────────────┬─────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│ SALIDA                                              │
│ Excel (openpyxl) · Word (python-docx) · UI          │
└─────────────────────────────────────────────────────┘
```

**Clave:** la exportación se genera desde SQL, nunca desde el texto del LLM.

---

## Slide 4 — Cómo responde una consulta

Ejemplo: *"¿Cómo votó cada bancada en la moción 19785?"*

1. **Router** detecta `intencion=agregacion`, `tipo=moción`, `proyecto_o_mocion=1486`.
2. **SQL** busca la votación y agrupa por bancada:
   - Fuerza Popular: 22 a favor, 0 en contra, 0 abstenciones.
   - Perú Libre: 0 a favor, 12 en contra, 0 abstenciones.
3. **LLM** redacta la respuesta usando solo esas filas.
4. **Cita** devuelve `acta_id`, `pagina_inicio` y `pdf_url`.
5. **Export** genera Excel/Word desde el mismo resultado.

En ningún paso el LLM cuenta votos.

---

## Slide 5 — Stack y alcance

| Componente | Elección | Motivo |
|---|---|---|
| DB estructurada | SQLite | Exactitud, cero servidor |
| Vector store | ChromaDB | Local, persistente |
| Embeddings | `multilingual-e5-small` | Español, 118 MB |
| LLM | Ollama `qwen2.5:7b` / Gemini | Local por defecto; API opcional |
| UI | Streamlit | Prototipo rápido |
| Export | openpyxl + python-docx | Formatos editables |
| Python | 3.12 | Compatibilidad con PyTorch |

**Alcance cargado:** 2 legislaturas (`2025-2026-L1`, `2025-2026-L2`).

| Métrica | Valor |
|---|---|
| Actas | 41 |
| Votaciones | 676 |
| Filas de voto | 62,537 |
| Congresistas | 132 |
| Bancadas | 14 |
| Páginas | 4,619 |

---

## Slide 6 — Por qué no alucina

1. **Los números no los produce el LLM.** Salen de consultas SQL parametrizadas.
2. **Toda respuesta lleva cita:** acta, página y enlace al PDF original.
3. **Si no hay evidencia, no responde:** devuelve "No se encontró evidencia en el corpus".
4. **La tabla exportada es reproducible:** mismos filtros, misma tabla.
5. **La confianza se muestra:** 5,974 votos con confianza alta y 56,563 con confianza media se etiquetan en la UI.

**No ocultamos la incertidumbre. La hacemos visible y auditable.**

---

## Slide 7 — Hallazgo del avance

Al comparar el pipeline anterior con los datos consolidados:

| Legislatura | `Congress_Analysis` | `ushnu-congreso` | Diferencia |
|---|---|---|---|
| 2025-2026-L1 | 402 | 402 | 0 |
| 2025-2026-L2 | 226 | 274 | **+48 votaciones** |

**Los datos consolidados contienen 21% más votaciones en la segunda legislatura que el pipeline anterior.**

Además, se elimina la corrida de ~5 horas de `scrap.py` y `pdf_to_csv.py`: las actas ya están extraídas a texto con página y las votaciones ya están consolidadas con nivel de confianza.

---

## Slide 8 — Estado y próximos pasos

### Completado
- Auditoría de las fuentes de datos.
- Definición del alcance: 41 actas, 676 votaciones.
- Arquitectura híbrida definida e implementada.
- Repositorio `Congress_RAG` con modelo SQLite e ingesta reproducible.
- `qa_report.csv`: 659/676 votaciones con integridad verificada (97.5%).
- 2,499 chunks generados (676 de votación + 1,823 narrativos).
- Router, SQL tools y cadena RAG determinista con citas.
- UI Streamlit (ingesta, consulta, explorador y calidad) y exportación a Excel/Word.
- 34 tests unitarios pasando.

### En curso
- Índice vectorial en ChromaDB (dependencia pesada, opcional para la demo).
- Evaluación con LLM local y set dorado ampliado.

### Próximos hitos
1. Poblar ChromaDB y activar recuperación narrativa.
2. Medir precisión del router y de las respuestas con Ollama.
3. Ampliar el alcance a legislaturas anteriores.

---

## Slide 9 — Limitaciones declaradas

| Limitación | Estado |
|---|---|
| 90% de los votos tienen confianza `media` | Se etiqueta en la UI y se puede filtrar |
| Solo 2 legislaturas cargadas | El sistema declara el alcance antes de responder |
| Texto OCR con ruido | Capa de normalización con tests |
| LLM local puede ser lento en CPU | `qwen2.5:7b` cuantizado; Gemini como opción |
| El corpus no incluye debate completo | Chunks narrativos del acta, no transcripción taquigráfica |

---

## Guion de exposición (6–8 minutos)

| Min | Slide | Qué decir |
|---|---|---|
| 0:00 | 1 | "El problema no es que falten datos: es que están en PDF no tabulares y revisarlos es manual." |
| 1:00 | 2 | "La tentación es un RAG puro. No alcanza: un top-k no suma votos. Por eso separamos números de contexto." |
| 2:30 | 3 | Recorrer el diagrama de izquierda a derecha: fuentes → ingesta → consulta → salida. |
| 3:30 | 4 | Contar el ejemplo de la moción 19785 paso a paso. Enfatizar: "el LLM no cuenta". |
| 5:00 | 5 | Mostrar stack y métricas. "Esto no es una maqueta: son 676 votaciones reales." |
| 5:45 | 6 | Explicar las 5 garantías anti-alucinación. |
| 6:30 | 7 | Mostrar el hallazgo de las +48 votaciones y las 5 horas ahorradas. |
| 7:15 | 8 | Cerrar con estado y próximos hitos. |
| 7:45 | 9 | Declarar limitaciones antes de que las pregunten. |

---

## Preguntas probables y respuestas

**¿Por qué no usar solo un LLM con los PDFs?**
Porque los PDFs no son tabulares y el LLM no es una base de datos. Para conteos necesitamos SQL; para contexto, recuperación semántica.

**¿Cómo evitan que invente cifras?**
El LLM no calcula. Recibe filas ya agregadas por SQL y solo las redacta. Toda cifra es trazable a una consulta.

**¿Por qué no GPT-4 o Gemini por defecto?**
El objetivo es costo cero y funcionamiento local. La arquitectura abstrae el proveedor: cambiar a Gemini es una variable de entorno.

**¿Qué pasa si el acta tiene errores de OCR?**
Se normaliza el texto y se valida contra los conteos declarados en el propio acta. Las votaciones inconsistentes se marcan en `qa_report.csv` y en la UI.

**¿Por qué solo dos legislaturas?**
Porque el alcance de la presentación es un prototipo verificable. La ingesta es idempotente y parametrizada: ampliar el rango es cambiar un filtro.

**¿Esto reemplaza al análisis estadístico existente?**
No. Lo complementa: `Congress_Analysis` mide cohesión y dimensiones; `Congress_RAG` permite consultar y auditar votaciones individuales.

---

## Resumen para la diapositiva final

> **Congress_RAG convierte 4,619 páginas de actas en un corpus consultable, con cifras exactas, fuentes citadas y exportación reproducible.**
>
> La clave no es un LLM más grande: es separar los números (SQL) del lenguaje (LLM).
