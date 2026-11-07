"""Prompts con reglas explícitas anti-alucinación."""

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


def build_user_prompt(
    pregunta: str,
    tabla: TableSpec | None = None,
    contexto: str = "",
    fuentes: list[str] | None = None,
) -> str:
    partes = [SYSTEM_PROMPT, "", f"PREGUNTA: {pregunta}"]

    if tabla and tabla.filas:
        partes.extend(["", f"TABLA ({tabla.titulo}):"])
        partes.append(" | ".join(tabla.columnas))
        for fila in tabla.filas:
            partes.append(" | ".join("" if valor is None else str(valor) for valor in fila))

    if contexto:
        partes.extend(["", "CONTEXTO:", contexto[:6000]])

    if fuentes:
        partes.extend(["", "FUENTES DISPONIBLES:", *fuentes])

    partes.extend(["", "RESPUESTA:"])
    return "\n".join(partes)
