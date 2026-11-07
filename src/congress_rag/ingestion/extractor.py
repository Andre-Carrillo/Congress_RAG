"""Extracción de texto de actas con referencia de página."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from congress_rag.ingestion.normalize import PAGE_MARKER_RE


class Page(BaseModel):
    numero: int
    texto: str


def split_pages(text: str) -> list[Page]:
    """Divide el texto de un acta usando los marcadores ``===== PAGINA N =====``."""

    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [Page(numero=1, texto=text)] if text.strip() else []

    pages: list[Page] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages.append(Page(numero=int(match.group(1)), texto=text[start:end].strip()))
    return pages


def load_pages(path: Path | str) -> list[Page]:
    text = Path(path).read_text(encoding="utf-8")
    return split_pages(text)


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def slice_positions(text: str, start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    start = max(0, int(start))
    end = len(text) if end is None else min(len(text), int(end))
    return text[start:end]


def page_for_offset(text: str, offset: int) -> int:
    """Devuelve el número de página que contiene un desplazamiento de caracteres."""

    page = 1
    for match in PAGE_MARKER_RE.finditer(text):
        if match.start() > offset:
            break
        page = int(match.group(1))
    return page
