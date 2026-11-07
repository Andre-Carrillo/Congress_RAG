"""Pruebas de extracción y segmentación por página."""

from __future__ import annotations

from pathlib import Path

from congress_rag.ingestion.extractor import (
    load_pages,
    page_for_offset,
    slice_positions,
    split_pages,
)


def test_split_pages_respeta_marcadores() -> None:
    texto = (
        "===== PAGINA 1 =====\n"
        "Primera página.\n"
        "\n"
        "===== PAGINA 2 =====\n"
        "Segunda página.\n"
    )
    paginas = split_pages(texto)
    assert [pagina.numero for pagina in paginas] == [1, 2]
    assert paginas[0].texto == "Primera página."
    assert paginas[1].texto == "Segunda página."


def test_split_pages_sin_marcadores_devuelve_una_pagina() -> None:
    paginas = split_pages("Texto sin marcadores")
    assert len(paginas) == 1
    assert paginas[0].numero == 1


def test_split_pages_texto_vacio() -> None:
    assert split_pages("   \n") == []


def test_page_for_offset() -> None:
    texto = (
        "===== PAGINA 1 =====\n"
        "abc\n"
        "===== PAGINA 2 =====\n"
        "def\n"
    )
    assert page_for_offset(texto, 0) == 1
    assert page_for_offset(texto, texto.index("abc")) == 1
    assert page_for_offset(texto, texto.index("def")) == 2


def test_slice_positions_recorta_y_acota() -> None:
    texto = "0123456789"
    assert slice_positions(texto, 2, 5) == "234"
    assert slice_positions(texto, None, 5) == ""
    assert slice_positions(texto, 5, 999) == "56789"
    assert slice_positions(texto, -3, 3) == "012"


def test_load_pages(tmp_path: Path) -> None:
    ruta = tmp_path / "acta.txt"
    ruta.write_text("===== PAGINA 1 =====\nHola\n", encoding="utf-8")
    paginas = load_pages(ruta)
    assert len(paginas) == 1
    assert paginas[0].texto == "Hola"
