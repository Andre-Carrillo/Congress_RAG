"""Búsqueda semántica pura sobre el índice vectorial, sin LLM.

Este endpoint es la prueba de que la recuperación funciona por sí sola: recibe
una consulta, devuelve pasajes literales con acta, página y similitud, y no
invoca ningún proveedor de lenguaje.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from congress_rag.api.deps import (
    get_db,
    get_retriever_narrativa,
    get_retriever_votaciones,
)
from congress_rag.api.schemas import RespuestaBusqueda, ResultadoBusqueda
from congress_rag.config import settings
from congress_rag.db.models import Documento

router = APIRouter(prefix="/buscar", tags=["búsqueda"])


@router.get("", response_model=RespuestaBusqueda)
def buscar(
    q: Annotated[str, Query(min_length=3, max_length=500, description="Texto a buscar")],
    tipo: Annotated[
        Literal["narrativa", "votaciones"],
        Query(description="Colección a consultar: prosa de actas o bloques de votación"),
    ] = "narrativa",
    acta_id: Annotated[
        str | None, Query(description="Acota la búsqueda a un acta, p. ej. 2026-06-03-10")
    ] = None,
    legislatura: Annotated[
        str | None, Query(description="Acota a una legislatura, p. ej. 2025-2026-L2")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    min_score: Annotated[
        float | None,
        Query(
            ge=0.0,
            le=1.0,
            description="Similitud mínima; si se omite se usa el umbral de la colección",
        ),
    ] = None,
    session: Session = Depends(get_db),
) -> RespuestaBusqueda:
    """Devuelve pasajes literales ordenados por similitud. No usa LLM."""

    retriever = get_retriever_narrativa() if tipo == "narrativa" else get_retriever_votaciones()
    if retriever is None:
        return RespuestaBusqueda(
            consulta=q,
            coleccion=tipo,
            total=0,
            advertencias=[
                "El índice vectorial no está disponible. Genera los embeddings con "
                "`uv run python scripts/build_index.py`."
            ],
        )

    where: dict[str, str] = {}
    if acta_id:
        where["acta_id"] = acta_id
    if legislatura:
        where["legislatura_id"] = legislatura.upper()

    umbral = (
        min_score
        if min_score is not None
        else settings.min_score_narrativa
        if tipo == "narrativa"
        else settings.min_score
    )

    try:
        resultados = retriever.search(q, top_k=limit, where=where or None, min_score=umbral)
    except Exception as exc:
        return RespuestaBusqueda(
            consulta=q,
            coleccion=tipo,
            total=0,
            advertencias=[f"No se pudo consultar el índice vectorial: {exc}"],
        )

    actas = {
        str(item["metadata"].get("acta_id") or "")
        for item in resultados
        if item["metadata"].get("acta_id")
    }
    pdfs: dict[str, str | None] = {}
    if actas:
        pdfs = {
            acta: url
            for acta, url in session.execute(
                select(Documento.acta_id, Documento.pdf_url).where(
                    Documento.acta_id.in_(sorted(actas))
                )
            ).all()
        }

    items = [
        ResultadoBusqueda(
            acta_id=str(item["metadata"].get("acta_id") or ""),
            pagina=item["metadata"].get("pagina"),
            score=round(float(item["score"]), 4),
            texto=str(item["texto"]),
            votacion_id=item["metadata"].get("votacion_id") or None,
            pdf_url=pdfs.get(str(item["metadata"].get("acta_id") or "")),
        )
        for item in resultados
    ]
    return RespuestaBusqueda(consulta=q, coleccion=tipo, total=len(items), resultados=items)
