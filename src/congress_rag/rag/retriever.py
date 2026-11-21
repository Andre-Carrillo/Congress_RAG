"""Recuperación semántica sobre ChromaDB.

Cada colección tiene un propósito distinto y se consulta por separado:

- ``narrativa``: prosa de las actas, para preguntas de debate o contexto.
- ``votaciones``: bloques de votación, como respaldo del filtro SQL.

``min_score`` puede fijarse por instancia; si no, se usa el valor de ``settings``.
"""

from __future__ import annotations

from typing import Any

from congress_rag.config import settings
from congress_rag.indexing.embeddings import Embedder
from congress_rag.indexing.vector_store import ChromaStore


class Retriever:
    def __init__(
        self,
        # Se conserva el valor histórico por compatibilidad. Las rutas nuevas
        # siempre inyectan explícitamente la colección que necesitan.
        collection: str = "votaciones",
        *,
        embedder: Embedder | None = None,
        store: ChromaStore | None = None,
        min_score: float | None = None,
    ) -> None:
        self.collection = collection
        self.embedder = embedder or Embedder()
        self.store = store or ChromaStore(collection=collection)
        self.min_score = min_score

    def search(
        self,
        pregunta: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        top_k = top_k or settings.top_k
        umbral = (
            min_score
            if min_score is not None
            else self.min_score
            if self.min_score is not None
            else settings.min_score
        )
        embedding = self.embedder.encode_query(pregunta)
        resultados = self.store.search(embedding, top_k=top_k, where=where)
        return [item for item in resultados if item["score"] >= umbral]
