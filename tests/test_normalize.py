"""Pruebas de normalización de texto de actas."""

from __future__ import annotations

from congress_rag.ingestion.normalize import (
    clean_acta_text,
    normalize_key,
    normalize_title,
    split_names,
)


def test_normalize_key_resuelve_ruido_de_ocr() -> None:
    assert normalize_key("MOCI ÓN 1486") == normalize_key("Moción 1486")
    assert normalize_key("CONG RESISTAS QUE VOTARON") == "CONGRESISTASQUEVOTARON"
    assert normalize_key("") == ""


def test_normalize_key_elimina_acentos() -> None:
    assert normalize_key("Abstención") == "ABSTENCION"
    assert normalize_key("Sí") == "SI"


def test_normalize_title_colapsa_espacios() -> None:
    assert normalize_title("  REGISTRO   DIGITAL  DE VOTACIÓN. ") == (
        "REGISTRO DIGITAL DE VOTACIÓN"
    )
    assert normalize_title("") == ""


def test_split_names_separa_comas_y_conjunciones() -> None:
    nombres = split_names("Héctor Acuña Peralta, Agüero Gutiérrez y Aguinaga Recuenco")
    assert nombres == ["Héctor Acuña Peralta", "Agüero Gutiérrez", "Aguinaga Recuenco"]


def test_split_names_descarta_texto_narrativo() -> None:
    bloque = (
        "Héctor Acuña Peralta, el congresista que presidió la sesión y explicó "
        "el procedimiento completo ante el pleno durante varios minutos"
    )
    assert split_names(bloque) == ["Héctor Acuña Peralta"]


def test_clean_acta_text_quita_encabezados_y_pies() -> None:
    crudo = (
        "DEPARTAMENTO DE RELATORÍA, AGENDA Y ACTAS\n"
        "ÁREA DE REDACCIÓN DE ACTAS\n"
        "- 9 -\n"
        "Contenido real de la sesión.\n"
    )
    limpio = clean_acta_text(crudo)
    assert "Contenido real de la sesión." in limpio
    assert "RELATORÍA" not in limpio
    assert "- 9 -" not in limpio
