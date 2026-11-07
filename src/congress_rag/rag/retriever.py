"""Recuperación semántica sobre ChromaDB."""

from __future__ import annotations

from typing import Any

from congress_rag.config import settings
from congress_rag.indexing.embeddings import Embedder
from congress_rag.indexing.vector_store import ChromaStore


class Retriever:
    def __init__(
        self,
        collection: str = "votaciones",
        *,
        embedder: Embedder | None = None,
        store: ChromaStore | None = None,
    ) -> None:
        self.embedder = embedder or Embedder()
        self.store = store or ChromaStore(collection=collection)

    def search(
        self,
        pregunta: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        top_k = top_k or settings.top_k
        min_score = settings.min_score if min_score is None else min_score
        embedding = self.embedder.encode_query(pregunta)
        resultados = self.store.search(embedding, top_k=top_k, where=where)
        return [item for item in resultados if item["score"] >= min_score]
