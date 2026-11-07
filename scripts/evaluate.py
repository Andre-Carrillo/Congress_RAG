#!/usr/bin/env python
"""Evaluación básica sobre un set de preguntas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from congress_rag.config import settings
from congress_rag.db.session import get_engine, get_session
from congress_rag.rag.chain import answer_question
from congress_rag.rag.llm import get_provider
from congress_rag.rag.retriever import Retriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el set dorado de preguntas")
    parser.add_argument("--preguntas", default="eval/preguntas.csv")
    parser.add_argument(
        "--salida", default=str(settings.data_dir / "processed/eval_resultados.csv")
    )
    parser.add_argument("--sin-llm", action="store_true")
    args = parser.parse_args()

    ruta = Path(args.preguntas)
    if not ruta.exists():
        print(f"No existe {ruta}. Crea el set dorado primero.")
        return 1

    preguntas = pd.read_csv(ruta, encoding="utf-8-sig")
    if "pregunta" not in preguntas.columns:
        print("El CSV debe tener una columna 'pregunta'.")
        return 1

    provider = None if args.sin_llm else get_provider()
    try:
        retriever = Retriever()
    except Exception:
        retriever = None

    engine = get_engine(settings.db_path)
    resultados: list[dict[str, object]] = []
    with get_session(engine) as session:
        for _, fila in preguntas.iterrows():
            answer = answer_question(
                session,
                str(fila["pregunta"]),
                provider=provider,
                retriever=retriever,
                use_llm=not args.sin_llm,
            )
            resultados.append(
                {
                    "pregunta": answer.pregunta,
                    "esperado": fila.get("esperado", ""),
                    "respuesta": answer.respuesta,
                    "confianza": answer.confianza,
                    "n_fuentes": len(answer.fuentes),
                    "advertencias": " | ".join(answer.advertencias),
                }
            )

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(resultados).to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"Resultados: {salida} ({len(resultados)} preguntas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
