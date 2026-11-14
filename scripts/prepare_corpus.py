#!/usr/bin/env python
"""Prepara el corpus ya scrapeado que necesita el proyecto.

Copia y filtra los artefactos del pipeline de ``ushnu-congreso`` (actas en
texto, sesiones, votaciones y votos consolidados) al directorio
``data/corpus``. No descarga PDFs ni ejecuta el scraper: reutiliza el corpus
público ya extraído.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from congress_rag.config import settings  # noqa: E402

ENCODING = "utf-8-sig"
PUBLICOS = "datos/publicos"


def _leer_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding=ENCODING, dtype=str, keep_default_na=False)


def _escribir_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding=ENCODING)


def _filtrar_votos(origen: Path, destino: Path, votacion_ids: set[str]) -> int:
    """Filtra el CSV largo de votos por streaming para no cargar 93 MB en RAM."""

    destino.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    primero = True
    for chunk in pd.read_csv(
        origen,
        encoding=ENCODING,
        dtype=str,
        keep_default_na=False,
        chunksize=100_000,
    ):
        seleccion = chunk[chunk["votacion_id"].isin(votacion_ids)]
        if seleccion.empty:
            continue
        seleccion.to_csv(
            destino,
            mode="w" if primero else "a",
            header=primero,
            index=False,
            encoding=ENCODING,
        )
        primero = False
        total += len(seleccion)
    return total


def preparar_corpus(origen: Path, destino: Path, legislaturas: list[str]) -> dict[str, object]:
    if not (origen / PUBLICOS / "sesiones.csv").exists():
        raise FileNotFoundError(
            f"No se encontró el corpus de origen en {origen}. "
            "Indica la ruta con --origen."
        )

    sesiones = _leer_csv(origen / PUBLICOS / "sesiones.csv")
    sesiones = sesiones[sesiones["legislatura_codigo"].isin(legislaturas)].copy()
    if sesiones.empty:
        raise ValueError(f"No hay sesiones para las legislaturas {legislaturas}")
    acta_ids = set(sesiones["acta_id"])

    votaciones = _leer_csv(origen / PUBLICOS / "votaciones.csv")
    votaciones = votaciones[votaciones["acta_id"].isin(acta_ids)].copy()
    votacion_ids = set(votaciones["votacion_id"])

    registro = _leer_csv(origen / PUBLICOS / "registro_extraccion.csv")
    registro = registro[registro["acta_id"].isin(acta_ids)].copy()

    _escribir_csv(sesiones, destino / PUBLICOS / "sesiones.csv")
    _escribir_csv(votaciones, destino / PUBLICOS / "votaciones.csv")
    _escribir_csv(registro, destino / PUBLICOS / "registro_extraccion.csv")

    for nombre in ("congresistas_oficiales_actuales.csv", "bancadas_resueltas_general.csv"):
        shutil.copy2(origen / PUBLICOS / nombre, destino / PUBLICOS / nombre)

    filas_votos = _filtrar_votos(
        origen / PUBLICOS / "votos_largo_consolidado.csv",
        destino / PUBLICOS / "votos_largo_consolidado.csv",
        votacion_ids,
    )

    actas_copiadas = 0
    for ruta_relativa in sesiones["ruta_texto"]:
        if not ruta_relativa:
            continue
        origen_texto = origen / ruta_relativa
        destino_texto = destino / ruta_relativa
        if not origen_texto.exists():
            continue
        destino_texto.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen_texto, destino_texto)
        actas_copiadas += 1

    legacy_origen = Path.home() / "Documents/dev/Congress_Analysis/votos_csv"
    legacy_destino = destino / "legacy/votos_csv"
    legacy_copiados: list[str] = []
    if legacy_origen.exists():
        legacy_destino.mkdir(parents=True, exist_ok=True)
        for archivo in sorted(legacy_origen.glob("*.csv")):
            shutil.copy2(archivo, legacy_destino / archivo.name)
            legacy_copiados.append(archivo.name)

    manifiesto = {
        "generado_en": datetime.now(UTC).isoformat(),
        "origen": str(origen),
        "legislaturas": legislaturas,
        "actas": len(sesiones),
        "actas_texto_copiadas": actas_copiadas,
        "votaciones": len(votaciones),
        "votos": filas_votos,
        "congresistas_oficiales": len(
            _leer_csv(origen / PUBLICOS / "congresistas_oficiales_actuales.csv")
        ),
        "legacy": legacy_copiados,
        "nota": (
            "Corpus ya extraído del proyecto ushnu-congreso. "
            "No se ejecutó scraping ni descarga de PDFs para generar estos archivos."
        ),
    }
    (destino / "manifest.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifiesto


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara el corpus ya scrapeado")
    parser.add_argument(
        "--origen",
        type=Path,
        default=Path.home() / "Documents/dev/ushnu-congreso",
        help="Ruta del proyecto ushnu-congreso",
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=ROOT / "data/corpus",
        help="Destino dentro del repositorio",
    )
    parser.add_argument(
        "--legislaturas",
        default=",".join(settings.legislaturas_list),
        help="Códigos de legislatura separados por coma",
    )
    args = parser.parse_args()

    legislaturas = [item.strip() for item in args.legislaturas.split(",") if item.strip()]
    manifiesto = preparar_corpus(args.origen, args.destino, legislaturas)

    print("Corpus preparado en", args.destino)
    print(
        f"  Actas: {manifiesto['actas']} · Votaciones: {manifiesto['votaciones']} · "
        f"Votos: {manifiesto['votos']}"
    )
    print(f"  Textos copiados: {manifiesto['actas_texto_copiadas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
