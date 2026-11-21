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
ACTA_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}-\d{2})\b")
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
    "debati",
    "debatio",
    "discut",
    "argument",
    "contexto",
    "se dijo",
    "resume",
    "resumen",
    "explica",
    "motivo",
    "sustent",
    "intervin",
    "interven",
    "expus",
    "expuso",
    "manifest",
]


def detectar_filtros(pregunta: str) -> Filtros:
    filtros = Filtros()
    match = LEGISLATURA_RE.search(pregunta)
    if match:
        filtros.legislatura = match.group(1).upper()

    # Un acta concreta permite acotar tanto la búsqueda textual como la SQL.
    match = ACTA_RE.search(pregunta)
    if match:
        filtros.acta_id = match.group(1)

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

    entidad_sql = bool(filtros.proyecto_o_mocion or filtros.acta_id)

    if agregacion and busqueda:
        intencion = "mixta"
    elif agregacion:
        intencion = "agregacion"
    elif busqueda and entidad_sql:
        # Tema del debate + entidad concreta: tabla y pasajes, sin taparse.
        intencion = "mixta"
    elif busqueda:
        intencion = "busqueda"
    elif entidad_sql:
        # Una entidad identificable sin tema explícito se resuelve en SQL.
        intencion = "agregacion"
    elif filtros.bancada or filtros.legislatura:
        intencion = "mixta"
    else:
        # Sin entidad ni señal de conteo, el texto de las actas es la evidencia.
        intencion = "busqueda"

    return QueryPlan(
        intencion=intencion,
        filtros=filtros,
        requiere_sql=intencion in {"agregacion", "mixta"},
        requiere_contexto=intencion in {"busqueda", "mixta"},
        consulta_reescrita=pregunta,
    )


def _fusionar_filtros(base: Filtros, propuesto: Filtros) -> Filtros:
    """Conserva las entidades detectadas por reglas y completa el resto con el LLM.

    El router heurístico reconoce mociones, proyectos, legislaturas y bancadas
    con expresiones regulares. Si el LLM devuelve un identificador más vago
    (por ejemplo ``19785`` en vez de ``moción 19785``), prevalece la regla para
    no seleccionar una votación distinta que también mencione el número.
    """

    datos = propuesto.model_dump()
    for campo in ("legislatura", "bancada", "tipo", "proyecto_o_mocion", "acta_id"):
        valor = getattr(base, campo)
        if valor:
            datos[campo] = valor
    return Filtros(**datos)


def _hay_entidades(filtros: Filtros) -> bool:
    return any(
        getattr(filtros, campo)
        for campo in ("legislatura", "bancada", "proyecto_o_mocion", "acta_id")
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
        "En filtros.proyecto_o_mocion escribe siempre la palabra y el número, "
        "por ejemplo 'moción 19785' o 'proyecto 186'.\n"
        "Bancadas posibles: " + ", ".join(BANCADAS) + ".\n"
        f"Consulta: {pregunta}"
    )
    try:
        plan = provider.generate(prompt, schema=QueryPlan)
        if isinstance(plan, QueryPlan):
            intencion = plan.intencion
            if intencion == "fuera_de_alcance" and _hay_entidades(heuristico.filtros):
                intencion = heuristico.intencion
            return QueryPlan(
                intencion=intencion,
                filtros=_fusionar_filtros(heuristico.filtros, plan.filtros),
                requiere_sql=plan.requiere_sql,
                requiere_contexto=plan.requiere_contexto,
                consulta_reescrita=plan.consulta_reescrita or heuristico.consulta_reescrita,
            )
    except Exception:
        pass
    return heuristico
