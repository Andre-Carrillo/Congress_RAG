"""Almacén vectorial ChromaDB con carga diferida."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from congress_rag.config import settings


class ChromaStore:
    def __init__(self, persist_dir: Path | str | None = None, collection: str = "votaciones"):
        self.persist_dir = Path(persist_dir or settings.chroma_dir)
        self.collection_name = collection
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            try:
                import chromadb
            except ImportError as exc:  # pragma: no cover - depende de extras
                raise RuntimeError("Falta chromadb. Instala con: uv sync --extra vector") from exc
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            cliente = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = cliente.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert(
        self,
        ids: list[str],
        textos: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        batch_size: int = 256,
    ) -> int:
        total = 0
        for inicio in range(0, len(ids), batch_size):
            fin = inicio + batch_size
            self.collection.upsert(
                ids=ids[inicio:fin],
                documents=textos[inicio:fin],
                embeddings=embeddings[inicio:fin],
                metadatas=metadatas[inicio:fin],
            )
            total += len(ids[inicio:fin])
        return total

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        resultado = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        documentos = (resultado.get("documents") or [[]])[0]
        metadatas = (resultado.get("metadatas") or [[]])[0]
        distancias = (resultado.get("distances") or [[]])[0]
        ids = (resultado.get("ids") or [[]])[0]

        return [
            {
                "id": ids[i],
                "texto": documentos[i],
                "metadata": metadatas[i],
                "distancia": distancias[i],
                "score": 1 - distancias[i],
            }
            for i in range(len(ids))
        ]

    def count(self) -> int:
        return int(self.collection.count())
