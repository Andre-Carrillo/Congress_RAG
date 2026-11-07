"""Pruebas de construcción de chunks autocontenidos."""

from __future__ import annotations

from congress_rag.ingestion.chunker import (
    _agrupar_por_bancada,
    _chunks_narrativos,
    render_votacion_chunk,
)

VOTOS = [
    {"nombre": "Ana Torres", "bancada": "Fuerza Popular", "posicion": 1},
    {"nombre": "Luis Vega", "bancada": "Fuerza Popular", "posicion": 1},
    {"nombre": "Eva Rojas", "bancada": "Perú Libre", "posicion": -1},
    {"nombre": "Pedro Paz", "bancada": "Perú Libre", "posicion": 0},
]


def test_agrupar_por_bancada() -> None:
    resumen = _agrupar_por_bancada(VOTOS)
    assert resumen["Fuerza Popular"] == {"si": 2, "no": 0, "abst": 0}
    assert resumen["Perú Libre"] == {"si": 0, "no": 1, "abst": 1}


def test_render_votacion_chunk_es_autocontenido() -> None:
    texto = render_votacion_chunk(
        titulo="MOCIÓN 1486",
        acta_id="2026-03-05-01",
        numero_sesion=12,
        pagina=8,
        legislatura="2025-2026-L2",
        votos=VOTOS,
        texto_bloque="Extracto de prueba.",
        conteo_si=2,
        conteo_no=1,
        conteo_abst=1,
    )
    assert "VOTACIÓN: MOCIÓN 1486" in texto
    assert "Acta 2026-03-05-01" in texto
    assert "Página 8" in texto
    assert "2 a favor, 1 en contra, 1 abstenciones" in texto
    assert "A FAVOR (2): Ana Torres, Luis Vega" in texto
    assert "EN CONTRA (1): Eva Rojas" in texto
    assert "ABSTENCIÓN (1): Pedro Paz" in texto
    assert "Fuerza Popular: 2 a favor, 0 en contra, 0 abstenciones" in texto
    assert "EXTRACTO DEL ACTA:" in texto
    assert "Extracto de prueba." in texto


def test_render_sin_texto_de_acta() -> None:
    texto = render_votacion_chunk(
        titulo="MOCIÓN 1",
        acta_id="2026-01-01-01",
        numero_sesion=None,
        pagina=None,
        legislatura="2025-2026-L1",
        votos=VOTOS,
        texto_bloque="",
        conteo_si=2,
        conteo_no=1,
        conteo_abst=1,
    )
    assert "EXTRACTO DEL ACTA" not in texto
    assert "Página ?" in texto


def test_chunks_narrativos_genera_fragmentos() -> None:
    texto = "Contenido narrativo del debate. " * 200
    chunks = _chunks_narrativos(
        texto,
        acta_id="2026-03-05-01",
        documento_pk=1,
        legislatura="2025-2026-L2",
        intervalos=[],
    )
    assert chunks
    assert all(chunk["metadata"]["tipo"] == "narrativa" for chunk in chunks)
    assert all(len(chunk["texto"]) >= 300 for chunk in chunks)
    assert chunks[0]["metadata"]["acta_id"] == "2026-03-05-01"


def test_chunks_narrativos_excluye_intervalos_de_votacion() -> None:
    texto = "Contenido narrativo del debate. " * 200
    chunks = _chunks_narrativos(
        texto,
        acta_id="2026-03-05-01",
        documento_pk=1,
        legislatura="2025-2026-L2",
        intervalos=[(0, len(texto) + 1)],
    )
    assert chunks == []
