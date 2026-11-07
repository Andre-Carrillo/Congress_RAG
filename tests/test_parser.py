"""Pruebas del parser de respaldo para actas nuevas."""

from __future__ import annotations

from congress_rag.ingestion.parser import parse_text

ACTA = """
===== PAGINA 8 =====

DEPARTAMENTO DE RELATORÍA, AGENDA Y ACTAS
ÁREA DE REDACCIÓN DE ACTAS
- 8 -

REGISTRO DIGITAL DE VOTACIÓN DE LA MOCIÓN 1486

CONGRESISTAS QUE VOTARON A FAVOR:
Héctor Acuña Peralta, Agüero Gutiérrez y Aguinaga Recuenco

CONGRESISTAS QUE VOTARON EN CONTRA:
Alva Prieto

CONGRESISTAS QUE SE ABSTUVIERON:
Arriola Tueros
"""


def test_parse_text_extrae_una_votacion() -> None:
    votaciones = parse_text(ACTA)
    assert len(votaciones) == 1
    votacion = votaciones[0]
    assert votacion.titulo == "DE LA MOCIÓN 1486"
    assert votacion.favor == [
        "Héctor Acuña Peralta",
        "Agüero Gutiérrez",
        "Aguinaga Recuenco",
    ]
    assert votacion.contra == ["Alva Prieto"]
    assert votacion.abstencion == ["Arriola Tueros"]


def test_parse_text_sin_votaciones() -> None:
    assert parse_text("Acta sin registro digital de votación.") == []


def test_parse_text_multiples_votaciones() -> None:
    acta = (
        ACTA
        + "\n\nREGISTRO DIGITAL DE VOTACIÓN DE LA CUESTIÓN PREVIA\n\n"
        "CONGRESISTAS QUE VOTARON A FAVOR:\n"
        "Bazán Narro\n"
    )
    votaciones = parse_text(acta)
    assert len(votaciones) == 2
    assert votaciones[1].titulo == "DE LA CUESTIÓN PREVIA"
    assert votaciones[1].favor == ["Bazán Narro"]
