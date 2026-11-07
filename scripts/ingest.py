#!/usr/bin/env python
"""Ingesta completa: ushnu-congreso -> SQLite + chunks + QA."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from congress_rag.ingestion.pipeline import run_chunks_only, run_ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta del corpus de actas")
    parser.add_argument(
        "--chunks-only",
        action="store_true",
        help="Solo regenera chunks.jsonl a partir de la base existente",
    )
    parser.add_argument(
        "--no-chunks",
        action="store_true",
        help="Carga la base y el QA, sin generar chunks",
    )
    args = parser.parse_args()

    if args.chunks_only:
        run_chunks_only()
    else:
        run_ingest(build_chunks=not args.no_chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
