"""Utilidades de limpieza y normalización de texto de actas."""

from __future__ import annotations

import re
import unicodedata

PAGE_MARKER_RE = re.compile(r"^=====\s*PAGINA\s+(\d+)\s*=====\s*$", re.MULTILINE | re.IGNORECASE)
FOOTER_RE = re.compile(
    r"S\s*[ÁA]\s*R\s*E\s*A\s*D\s*E\s*R\s*E\s*D\s*A\s*C\s*C\s*I\s*[ÓO]\s*N\s*D\s*E\s*A\s*C\s*T\s*A\s*S?",
    re.IGNORECASE,
)
HEADER_RE = re.compile(
    r"DEPARTAMENTO\s+DE\s+RELATOR[ÍI]A,?\s+AGENDA\s+Y\s+ACTAS[\s\S]{0,120}?"
    r"ÁREA\s+DE\s+REDACCI[ÓO]N\s+DE\s+ACTAS",
    re.IGNORECASE,
)
PAGE_NUMBER_RE = re.compile(r"^\s*-\s*\d{1,4}\s*-\s*$", re.MULTILINE)
SEPARATOR_RE = re.compile(r"^\s*-=o=-\s*$", re.MULTILINE)
MULTI_SPACE_RE = re.compile(r"[ \t]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalize_key(text: str) -> str:
    """Clave de comparación: mayúsculas, sin acentos y sin separadores.

    Resuelve el ruido de OCR del tipo ``MOCI ÓN`` vs ``MOCIÓN`` y
    ``CONG RESISTAS`` vs ``CONGRESISTAS``.
    """

    if not text:
        return ""
    text = strip_accents(str(text)).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_title(text: str) -> str:
    """Normaliza un título conservando legibilidad para mostrar en la UI."""

    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    # Algunos títulos del corpus arrastran encabezados de página del PDF.
    text = HEADER_RE.sub(" ", text)
    text = FOOTER_RE.sub(" ", text)
    text = PAGE_MARKER_RE.sub(" ", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip(" .-\n\t")


def collapse_spaces(text: str) -> str:
    return MULTI_SPACE_RE.sub(" ", text).strip()


def clean_acta_text(text: str, keep_page_markers: bool = False) -> str:
    """Limpia encabezados, pies y numeración de página del acta."""

    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = HEADER_RE.sub("", text)
    text = FOOTER_RE.sub("", text)
    text = PAGE_NUMBER_RE.sub("", text)
    text = SEPARATOR_RE.sub("", text)
    if not keep_page_markers:
        text = PAGE_MARKER_RE.sub("", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def split_names(block: str) -> list[str]:
    """Separa una lista de nombres separada por comas o conjunciones."""

    block = re.sub(r"\s+", " ", block).strip(" .;")
    if not block:
        return []
    parts = re.split(r",|\s+y\s+|\s+e\s+", block, flags=re.IGNORECASE)
    names: list[str] = []
    for part in parts:
        name = part.strip(" .;-\n\t")
        if not name:
            continue
        # Descarta fragmentos que en realidad son texto narrativo.
        if len(name) > 70 or len(name.split()) > 7:
            continue
        primera = name.split()[0].lower()
        if primera in {
            "el",
            "la",
            "los",
            "las",
            "un",
            "una",
            "unos",
            "unas",
            "que",
            "quien",
            "quienes",
            "del",
            "de",
            "en",
            "con",
            "por",
            "para",
            "al",
        }:
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", name):
            continue
        names.append(name)
    return names
