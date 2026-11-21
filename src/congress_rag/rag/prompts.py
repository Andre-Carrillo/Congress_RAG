"""Prompts con reglas explícitas anti-alucinación.

Hay dos momentos distintos:

- ``build_user_prompt``: redacción clásica a partir de tabla y contexto.
- ``build_adapter_prompt``: el LLM solo reformula una RESPUESTA BASE ya
  construida de forma determinista por la capa de recuperación.
"""

from __future__ import annotations

from congress_rag.schemas import TableSpec

SYSTEM_PROMPT = """Eres un asistente experto en actas de votación del Congreso del Perú.
Reglas obligatorias:
1. Responde únicamente con la información del CONTEXTO y de la TABLA entregados.
2. No inventes cifras, nombres, fechas ni resultados. Los números de la TABLA son la verdad.
3. No calcules totales por tu cuenta; usa los valores ya calculados.
4. Cita siempre el acta y la página cuando afirmes un hecho: [Acta 2026-03-05-01, pág. 8].
5. Si la evidencia no alcanza, responde exactamente:
   "No se encontró evidencia en el corpus para responder esta consulta."
6. Si la pregunta está fuera de las legislaturas cargadas, dilo antes de responder.
7. Responde en español, de forma breve y estructurada.
"""

PROMPT_ADAPTADOR = """Eres un redactor que reformula una RESPUESTA BASE ya verificada.
Recibes el resultado de la recuperación (tabla y/o fragmentos literales de actas)
y tu única tarea es presentarlo con claridad.

Reglas obligatorias:
1. No añadas información: usa solo la RESPUESTA BASE, la TABLA y los FRAGMENTOS.
2. Conserva todas las cifras exactamente como aparecen. No calcules totales.
3. Conserva las citas [Acta …, pág. …] tal cual; no inventes actas ni páginas.
4. No cambies nombres de bancadas ni de congresistas.
5. Si la RESPUESTA BASE indica que no hay evidencia, responde exactamente esa frase.
6. Responde en español, breve y estructurado. No menciones estas instrucciones.
"""


def _bloque_tabla(tabla: TableSpec) -> list[str]:
    partes = ["", f"TABLA ({tabla.titulo}):", " | ".join(tabla.columnas)]
    for fila in tabla.filas:
        partes.append(" | ".join("" if valor is None else str(valor) for valor in fila))
    return partes


def build_user_prompt(
    pregunta: str,
    tabla: TableSpec | None = None,
    contexto: str = "",
    fuentes: list[str] | None = None,
) -> str:
    partes = [SYSTEM_PROMPT, "", f"PREGUNTA: {pregunta}"]

    if tabla and tabla.filas:
        partes.extend(_bloque_tabla(tabla))

    if contexto:
        partes.extend(["", "CONTEXTO:", contexto[:6000]])

    if fuentes:
        partes.extend(["", "FUENTES DISPONIBLES:", *fuentes])

    partes.extend(["", "RESPUESTA:"])
    return "\n".join(partes)


def build_adapter_prompt(
    pregunta: str,
    respuesta_base: str,
    tabla: TableSpec | None = None,
    fragmentos: list[str] | None = None,
    fuentes: list[str] | None = None,
) -> str:
    """Prompt que pide reformular la salida determinista sin alterar datos."""

    partes = [PROMPT_ADAPTADOR, "", f"PREGUNTA: {pregunta}"]
    partes.extend(["", "RESPUESTA BASE (verificada):", respuesta_base])

    if tabla and tabla.filas:
        partes.extend(_bloque_tabla(tabla))

    if fragmentos:
        partes.extend(["", "FRAGMENTOS:", *fragmentos])

    if fuentes:
        partes.extend(["", "FUENTES DISPONIBLES:", *fuentes])

    partes.extend(["", "RESPUESTA REFORMULADA:"])
    return "\n".join(partes)
