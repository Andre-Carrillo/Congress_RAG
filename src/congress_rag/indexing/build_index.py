"""Construcción del índice vectorial a partir de ``chunks.jsonl``."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from congress_rag.config import Settings, settings
from congress_rag.indexing.embeddings import Embedder
from congress_rag.indexing.vector_store import ChromaStore

COLECCIONES = {"votacion": "votaciones", "narrativa": "narrativa"}


def leer_chunks(cfg: Settings | None = None) -> list[dict[str, Any]]:
    cfg = cfg or settings
    with cfg.chunks_path.open(encoding="utf-8") as handle:
        return [json.loads(linea) for linea in handle if linea.strip()]


def _metadata_plana(metadata: dict[str, Any]) -> dict[str, Any]:
    limpia: dict[str, Any] = {}
    for clave, valor in metadata.items():
        if valor is None:
            continue
        if isinstance(valor, (str, int, float, bool)):
            limpia[clave] = valor
        else:
            limpia[clave] = str(valor)
    return limpia


def build_index(
    cfg: Settings | None = None,
    *,
    tipos: Iterable[str] = ("votacion", "narrativa"),
    verbose: bool = True,
) -> dict[str, int]:
    cfg = cfg or settings
    chunks = leer_chunks(cfg)
    embedder = Embedder(cfg.embedding_model)
    resultado: dict[str, int] = {}

    for tipo in tipos:
        coleccion = COLECCIONES.get(tipo)
        if not coleccion:
            continue
        seleccion = [chunk for chunk in chunks if chunk["metadata"].get("tipo") == tipo]
        if not seleccion:
            resultado[coleccion] = 0
            continue

        ids = [chunk["id"] for chunk in seleccion]
        textos = [chunk["texto"] for chunk in seleccion]
        metadatas = [_metadata_plana(chunk["metadata"]) for chunk in seleccion]
        embeddings = embedder.encode_passages(textos)

        store = ChromaStore(cfg.chroma_dir, collection=coleccion)
        insertados = store.upsert(ids, textos, embeddings, metadatas)
        resultado[coleccion] = insertados
        if verbose:
            print(f"  {coleccion}: {insertados} chunks indexados")

    return resultado
