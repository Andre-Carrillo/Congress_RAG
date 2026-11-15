"""Ejecuta la API con uvicorn usando la configuración del proyecto.

Uso::

    uv run python -m congress_rag.api
    uv run python -m congress_rag.api --host 0.0.0.0 --port 8080 --reload
"""

from __future__ import annotations

import argparse

import uvicorn

from congress_rag.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor HTTP de Congress_RAG")
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument("--reload", action="store_true", help="Recarga en caliente para desarrollo")
    args = parser.parse_args()

    uvicorn.run(
        "congress_rag.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
