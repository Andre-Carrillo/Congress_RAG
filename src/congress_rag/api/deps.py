"""Dependencias compartidas por los endpoints: sesión SQLite, retriever y LLM."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from congress_rag.config import settings
from congress_rag.db.session import get_engine
from congress_rag.rag.llm import LLMProvider, get_provider
from congress_rag.rag.retriever import Retriever


@lru_cache(maxsize=4)
def _engine_para(ruta: str) -> Engine:
    return get_engine(ruta)


def get_db() -> Iterator[Session]:
    """Abre una sesión de solo lectura contra la base ya ingestada."""

    if not settings.db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No existe la base de datos. Ejecuta `uv run python scripts/ingest.py` "
                "antes de consumir la API."
            ),
        )
    engine = _engine_para(str(settings.db_path))
    with Session(engine, expire_on_commit=False) as session:
        yield session


@lru_cache(maxsize=1)
def _retriever_cache() -> Retriever | None:
    try:
        return Retriever()
    except Exception:
        # Sin extras de embeddings/Chroma la API sigue respondiendo desde SQL.
        return None


def get_retriever() -> Retriever | None:
    return _retriever_cache()


def resolver_llm(usar_llm: bool) -> tuple[LLMProvider | None, list[str]]:
    """Devuelve el proveedor LLM y las advertencias si no se puede construir."""

    if not usar_llm:
        return None, []

    try:
        return get_provider(), []
    except Exception as exc:
        return None, [f"LLM no disponible: {exc}"]


def reset_caches() -> None:
    """Limpia las dependencias memorizadas (útil en pruebas)."""

    _engine_para.cache_clear()
    _retriever_cache.cache_clear()
