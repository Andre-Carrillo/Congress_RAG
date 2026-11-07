"""Exportación reproducible a Excel desde un ``Answer``."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from congress_rag.schemas import Answer

COLORES_VOTO = {
    "A favor": "C6EFCE",
    "En contra": "FFC7CE",
    "Abstención": "EDEDED",
    "No votó": "FFF2CC",
}


def to_excel(answer: Answer) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Respuesta"

    ws["A1"] = "Pregunta"
    ws["A1"].font = Font(bold=True)
    ws["B1"] = answer.pregunta
    ws["A2"] = "Respuesta"
    ws["A2"].font = Font(bold=True)
    ws["B2"] = answer.respuesta
    ws["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["A3"] = "Confianza"
    ws["A3"].font = Font(bold=True)
    ws["B3"] = answer.confianza

    fila_actual = 5
    if answer.tabla:
        ws.cell(row=fila_actual, column=1, value=answer.tabla.titulo).font = Font(bold=True)
        fila_actual += 1
        for columna, titulo in enumerate(answer.tabla.columnas, start=1):
            celda = ws.cell(row=fila_actual, column=columna, value=titulo)
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="1F4E78")
            celda.alignment = Alignment(horizontal="center", wrap_text=True)
        fila_actual += 1

        for fila in answer.tabla.filas:
            for columna, valor in enumerate(fila, start=1):
                celda = ws.cell(row=fila_actual, column=columna, value=valor)
                celda.alignment = Alignment(wrap_text=True, vertical="top")
                color = COLORES_VOTO.get(str(valor))
                if color:
                    celda.fill = PatternFill("solid", fgColor=color)
            fila_actual += 1

        for columna in range(1, len(answer.tabla.columnas) + 1):
            ws.column_dimensions[get_column_letter(columna)].width = 22
        ws.freeze_panes = ws.cell(row=6, column=1)

    fuentes = wb.create_sheet("Fuentes")
    for columna, titulo in enumerate(["Acta", "Página", "Votación", "URL PDF"], start=1):
        celda = fuentes.cell(row=1, column=columna, value=titulo)
        celda.font = Font(bold=True)
    for indice, fuente in enumerate(answer.fuentes, start=2):
        fuentes.cell(row=indice, column=1, value=fuente.acta_id)
        fuentes.cell(row=indice, column=2, value=fuente.pagina)
        fuentes.cell(row=indice, column=3, value=fuente.votacion_id)
        fuentes.cell(row=indice, column=4, value=fuente.pdf_url)
    fuentes.column_dimensions["A"].width = 24
    fuentes.column_dimensions["D"].width = 80

    metadatos = wb.create_sheet("Metadatos")
    metadatos["A1"] = "Generado por"
    metadatos["B1"] = "Congress_RAG"
    metadatos["A2"] = "Advertencias"
    metadatos["B2"] = " | ".join(answer.advertencias)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
