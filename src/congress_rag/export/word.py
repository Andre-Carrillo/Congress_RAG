"""Exportación reproducible a Word desde un ``Answer``."""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.shared import Pt

from congress_rag.schemas import Answer


def to_word(answer: Answer) -> bytes:
    documento = Document()
    documento.add_heading("Congress_RAG · Consulta a actas de votación", level=1)

    documento.add_heading("Pregunta", level=2)
    documento.add_paragraph(answer.pregunta)

    documento.add_heading("Respuesta", level=2)
    documento.add_paragraph(answer.respuesta)

    if answer.tabla and answer.tabla.filas:
        documento.add_heading(answer.tabla.titulo, level=2)
        tabla = documento.add_table(rows=1, cols=len(answer.tabla.columnas))
        tabla.style = "Light Grid Accent 1"
        for indice, titulo in enumerate(answer.tabla.columnas):
            tabla.rows[0].cells[indice].text = str(titulo)
        for fila in answer.tabla.filas:
            celdas = tabla.add_row().cells
            for indice, valor in enumerate(fila):
                celdas[indice].text = "" if valor is None else str(valor)

    if answer.fuentes:
        documento.add_heading("Fuentes", level=2)
        for fuente in answer.fuentes:
            texto = f"Acta {fuente.acta_id}"
            if fuente.pagina:
                texto += f", página {fuente.pagina}"
            if fuente.votacion_id:
                texto += f" · {fuente.votacion_id}"
            parrafo = documento.add_paragraph(texto, style="List Bullet")
            parrafo.runs[0].font.size = Pt(9)

    if answer.advertencias:
        documento.add_heading("Advertencias", level=2)
        for advertencia in answer.advertencias:
            documento.add_paragraph(advertencia, style="List Bullet")

    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()
