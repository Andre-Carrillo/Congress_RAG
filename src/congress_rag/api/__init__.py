"""API HTTP (FastAPI) para consultar el corpus y la cadena RAG.

Arranque local::

    uv run python -m congress_rag.api

La documentación interactiva queda en ``http://127.0.0.1:8000/docs``.
"""

from __future__ import annotations

from congress_rag.api.app import create_app

__all__ = ["create_app"]
