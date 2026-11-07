"""Parser de respaldo para actas nuevas que aún no estén en ushnu-congreso.

El pipeline principal usa los CSV consolidados de ``ushnu-congreso``. Este
parser existe para incorporar PDFs nuevos sin depender de ese proyecto.
"""

from __future__ import annotations

import re

from congress_rag.ingestion.normalize import clean_acta_text, normalize_title, split_names
from congress_rag.schemas import ParsedVotacion

TITULO_RE = re.compile(
    r"REGISTRO\s+DIGITAL\s+DE\s+(?:LA\s+)?VOTACI[ÓO]N\s+(.*?)"
    r"(?=CONGRESISTAS\s+QUE\s+|REGISTRO\s+DIGITAL\s+DE|\Z)",
    re.DOTALL | re.IGNORECASE,
)

FAVOR_RE = re.compile(r"CONGRESISTAS?\s+QUE\s+VOTARON\s+A\s+FAVOR\s*:", re.IGNORECASE)
CONTRA_RE = re.compile(
    r"CONGRESISTAS?\s+QUE\s+(?:VOTARON\s+EN\s+CONTRA|VOT[ÓO]\s+EN\s+CONTRA)\s*:",
    re.IGNORECASE,
)
ABSTENCION_RE = re.compile(
    r"CONGRESISTAS?\s+QUE\s+SE\s+ABSTUVIERON\s*:|CONGRESISTA\s+QUE\s+SE\s+ABSTUVO\s*:",
    re.IGNORECASE,
)
CUALQUIER_HEADER_RE = re.compile(
    r"CONGRESISTAS?\s+QUE\s+(?:VOTARON|SE\s+ABSTUVIERON|VOT[ÓO])|"
    r"REGISTRO\s+DIGITAL\s+DE",
    re.IGNORECASE,
)


def _bloque(segmento: str, patron: re.Pattern[str]) -> str:
    match = patron.search(segmento)
    if not match:
        return ""
    resto = segmento[match.end() :]
    siguiente = CUALQUIER_HEADER_RE.search(resto)
    if siguiente:
        resto = resto[: siguiente.start()]
    return resto


def parse_text(text: str, default_page: int = 1) -> list[ParsedVotacion]:
    """Extrae votaciones de un acta en texto plano."""

    limpio = clean_acta_text(text, keep_page_markers=True)
    resultados: list[ParsedVotacion] = []

    for match in TITULO_RE.finditer(limpio):
        titulo = normalize_title(re.sub(r"\s+", " ", match.group(1)))
        if not titulo:
            continue
        # El cuerpo llega hasta el siguiente título de votación.
        inicio = match.end()
        siguiente_titulo = TITULO_RE.search(limpio, inicio)
        cuerpo = limpio[inicio : siguiente_titulo.start() if siguiente_titulo else len(limpio)]

        resultados.append(
            ParsedVotacion(
                titulo=titulo,
                favor=split_names(_bloque(cuerpo, FAVOR_RE)),
                contra=split_names(_bloque(cuerpo, CONTRA_RE)),
                abstencion=split_names(_bloque(cuerpo, ABSTENCION_RE)),
                pagina=default_page,
            )
        )

    return resultados
