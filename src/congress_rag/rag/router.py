"""Router de consultas: decide entre SQL, recuperación semántica o ambas."""

from __future__ import annotations

import re

from congress_rag.ingestion.normalize import normalize_key
from congress_rag.rag.llm import LLMProvider
from congress_rag.schemas import Filtros, QueryPlan

BANCADAS = [
    "Fuerza Popular",
    "Alianza para el Progreso",
    "Perú Libre",
    "Somos Perú",
    "Renovación Popular",
    "Juntos por el Perú",
    "Acción Popular",
    "Lealtad Nacional",
    "Avanza País",
    "Honor y Democracia",
    "Bloque Democrático Popular",
    "Bancada Socialista",
    "Podemos Perú",
    "No Agrupado",
]

LEGISLATURA_RE = re.compile(r"\b(20\d{2}-20\d{2}-L\d)\b", re.IGNORECASE)
MOCION_RE = re.compile(
    r"\b(?:moci[oó]n|mocion)\s+(?:de\s+orden\s+del\s+d[ií]a\s+)?(\d{1,5})\b",
    re.IGNORECASE,
)
PROYECTO_RE = re.compile(r"\bproyecto\s+(?:de\s+ley\s+)?(\d{1,5})\b", re.IGNORECASE)

PALABRAS_AGREGACION = [
    "cuántos",
    "cuantos",
    "cuántas",
    "cuantas",
    "conteo",
    "por bancada",
    "cada bancada",
    "lista",
    "listado",
    "abstenciones",
    "abstencion",
    "abstuvieron",
    "a favor",
    "en contra",
    "votó",
    "voto",
    "votaron",
    "resultado",
]
PALABRAS_BUSQUEDA = [
    "debate",
    "argumento",
    "argumentos",
    "contexto",
    "qué se dijo",
    "que se dijo",
    "resume",
    "resumen",
    "explica",
    "motivo",
]


def detectar_filtros(pregunta: str) -> Filtros:
    filtros = Filtros()
    match = LEGISLATURA_RE.search(pregunta)
    if match:
        filtros.legislatura = match.group(1).upper()

    for bancada in BANCADAS:
        if normalize_key(bancada) in normalize_key(pregunta):
            filtros.bancada = bancada
            break

    match = MOCION_RE.search(pregunta)
    if match:
        filtros.proyecto_o_mocion = f"moción {match.group(1)}"
        filtros.tipo = "moción"
    else:
        match = PROYECTO_RE.search(pregunta)
        if match:
            filtros.proyecto_o_mocion = f"proyecto {match.group(1)}"
            filtros.tipo = "proyecto"

    return filtros


def route_heuristic(pregunta: str) -> QueryPlan:
    filtros = detectar_filtros(pregunta)
    texto = normalize_key(pregunta)
    agregacion = any(normalize_key(palabra) in texto for palabra in PALABRAS_AGREGACION)
    busqueda = any(normalize_key(palabra) in texto for palabra in PALABRAS_BUSQUEDA)

    if agregacion and busqueda:
        intencion = "mixta"
    elif agregacion:
        intencion = "agregacion"
    elif busqueda:
        intencion = "busqueda"
    else:
        intencion = "mixta"

    return QueryPlan(
        intencion=intencion,
        filtros=filtros,
        requiere_sql=intencion in {"agregacion", "mixta"},
        requiere_contexto=intencion in {"busqueda", "mixta"},
        consulta_reescrita=pregunta,
    )


def route(pregunta: str, provider: LLMProvider | None = None) -> QueryPlan:
    heuristico = route_heuristic(pregunta)
    if provider is None:
        return heuristico

    prompt = (
        "Clasifica la siguiente consulta sobre votaciones del Congreso del Perú.\n"
        "Devuelve un QueryPlan. Usa intencion=agregacion para conteos y listas, "
        "busqueda para contexto del debate, mixta para ambas, fuera_de_alcance si "
        "no trata sobre el corpus.\n"
        "Bancadas posibles: " + ", ".join(BANCADAS) + ".\n"
        f"Consulta: {pregunta}"
    )
    try:
        plan = provider.generate(prompt, schema=QueryPlan)
        if isinstance(plan, QueryPlan):
            return plan
    except Exception:
        pass
    return heuristico
