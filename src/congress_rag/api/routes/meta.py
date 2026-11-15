"""Endpoints de catálogo: legislaturas, tipos, bancadas y actas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from congress_rag.api.deps import get_db
from congress_rag.api.schemas import (
    ActaResumen,
    BancadaResumen,
    LegislaturaResumen,
    PaginaActas,
)
from congress_rag.rag import sql_tools

router = APIRouter(tags=["catálogo"])


@router.get("/legislaturas", response_model=list[LegislaturaResumen])
def listar_legislaturas(session: Session = Depends(get_db)) -> list[LegislaturaResumen]:
    """Legislaturas cargadas, con cantidad de actas y votaciones."""

    return [LegislaturaResumen(**fila) for fila in sql_tools.listar_legislaturas(session)]


@router.get("/tipos", response_model=list[str])
def listar_tipos(session: Session = Depends(get_db)) -> list[str]:
    """Tipos de votación detectados (moción, proyecto, cuestión de confianza...)."""

    return sql_tools.listar_tipos(session)


@router.get("/bancadas", response_model=list[BancadaResumen])
def listar_bancadas(session: Session = Depends(get_db)) -> list[BancadaResumen]:
    """Bancadas con la cantidad de congresistas registrados."""

    return [BancadaResumen(**fila) for fila in sql_tools.listar_bancadas(session)]


@router.get("/actas", response_model=PaginaActas)
def listar_actas(
    legislatura: str | None = Query(None, description="Ej. 2025-2026-L1"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> PaginaActas:
    """Actas del corpus con su número de votaciones y enlace al PDF original."""

    items = sql_tools.listar_actas(
        session, legislatura=legislatura, limit=limit, offset=offset
    )
    return PaginaActas(
        total=sql_tools.contar_actas(session, legislatura=legislatura),
        limit=limit,
        offset=offset,
        items=[ActaResumen(**item) for item in items],
    )
