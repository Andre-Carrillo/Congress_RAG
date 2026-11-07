"""Pruebas del lector del corpus anterior (``votos_csv``)."""

from __future__ import annotations

from pathlib import Path

from congress_rag.ingestion.bootstrap import (
    _leer_legacy,
    _listar_legacy,
    cargar_legacy,
)


def _escribir_csv(ruta: Path, filas: list[list[str]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as handle:
        for fila in filas:
            handle.write(",".join(fila) + "\n")


def test_listar_legacy_ignora_archivos_sin_votaciones(tmp_path: Path) -> None:
    _escribir_csv(
        tmp_path / "votos_csv/5.1.csv",
        [["Congresista", "Moción 1"], ["Ana", "1"]],
    )
    _escribir_csv(
        tmp_path / "votos_csv/5.2.csv",
        [["Congresista", "Moción 2"], ["Ana", "-1"]],
    )
    _escribir_csv(tmp_path / "votos_csv/5.3.csv", [["Congresista"]])

    archivos = _listar_legacy(tmp_path, 2)
    assert [path.name for path in archivos] == ["5.1.csv", "5.2.csv"]


def test_listar_legacy_sin_carpeta(tmp_path: Path) -> None:
    assert _listar_legacy(tmp_path, 2) == []


def test_leer_legacy_cuenta_posiciones(tmp_path: Path) -> None:
    ruta = tmp_path / "5.1.csv"
    _escribir_csv(
        ruta,
        [
            ["Congresista", "Moción 1", "Moción 2"],
            ["Ana", "1", "-1"],
            ["Luis", "1", "0"],
            ["Eva", "0", "1"],
            ["Pedro", "2", "2"],
        ],
    )
    filas = _leer_legacy(ruta)
    assert filas[0] == {
        "titulo": "Moción 1",
        "legacy_si": 2,
        "legacy_no": 0,
        "legacy_abst": 1,
        "legacy_ausente": 1,
    }
    assert filas[1]["legacy_si"] == 1
    assert filas[1]["legacy_no"] == 1
    assert filas[1]["legacy_abst"] == 1


def test_cargar_legacy_asigna_legislaturas(tmp_path: Path) -> None:
    _escribir_csv(
        tmp_path / "votos_csv/5.1.csv",
        [["Congresista", "Moción L1"], ["Ana", "1"]],
    )
    _escribir_csv(
        tmp_path / "votos_csv/5.2.csv",
        [["Congresista", "Moción L2"], ["Ana", "-1"]],
    )
    data = cargar_legacy(tmp_path, ["2025-2026-L1", "2025-2026-L2"])
    assert data.archivos == {
        "2025-2026-L1": "5.1.csv",
        "2025-2026-L2": "5.2.csv",
    }
    assert [fila["legislatura"] for fila in data.rows] == [
        "2025-2026-L1",
        "2025-2026-L2",
    ]
