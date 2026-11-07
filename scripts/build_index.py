#!/usr/bin/env python
"""Construcción del índice vectorial en ChromaDB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from congress_rag.indexing.build_index import build_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa chunks.jsonl en ChromaDB")
    parser.add_argument(
        "--tipos",
        default="votacion,narrativa",
        help="Tipos de chunk a indexar, separados por coma",
    )
    args = parser.parse_args()

    tipos = tuple(item.strip() for item in args.tipos.split(",") if item.strip())
    resultado = build_index(tipos=tipos)
    print("Indexación completada:", resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
