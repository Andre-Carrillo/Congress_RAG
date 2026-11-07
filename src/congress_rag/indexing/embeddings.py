"""Embeddings multilingües con carga diferida."""

from __future__ import annotations

from functools import lru_cache

from congress_rag.config import settings


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model

    @property
    def model(self):
        return _cargar_modelo(self.model_name)

    @property
    def usa_prefijos(self) -> bool:
        return "e5" in self.model_name.lower()

    def encode_passages(self, textos: list[str]) -> list[list[float]]:
        if self.usa_prefijos:
            textos = [f"passage: {texto}" for texto in textos]
        return self.model.encode(
            textos,
            normalize_embeddings=True,
            show_progress_bar=len(textos) > 50,
        ).tolist()

    def encode_query(self, texto: str) -> list[float]:
        if self.usa_prefijos:
            texto = f"query: {texto}"
        return self.model.encode([texto], normalize_embeddings=True).tolist()[0]


@lru_cache(maxsize=2)
def _cargar_modelo(nombre: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - depende de extras
        raise RuntimeError(
            "Falta sentence-transformers. Instala con: uv sync --extra embeddings"
        ) from exc
    return SentenceTransformer(nombre)
