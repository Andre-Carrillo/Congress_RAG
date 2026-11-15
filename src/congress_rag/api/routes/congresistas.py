"""Endpoints de congresistas: padrón e historial de voto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from congress_rag.api.deps import get_db
from congress_rag.api.schemas import CongresistaResumen, TableResponse
from congress_rag.rag import sql_tools

router = APIRouter(prefix="/congresistas", tags=["congresistas"])


@router.get("", response_model=list[CongresistaResumen])
def buscar_congresistas(
    buscar: str | None = Query(None, description="Parte del nombre, sin distinguir tildes"),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_db),
) -> list[CongresistaResumen]:
    """Padrón de congresistas, filtrable por nombre."""

    filas = sql_tools.buscar_congresistas(session, texto=buscar, limit=limit)
    return [CongresistaResumen(**fila) for fila in filas]


@router.get("/{nombre}/historial", response_model=TableResponse)
def historial(
    nombre: str,
    legislatura: str | None = Query(None, description="Ej. 2025-2026-L1"),
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_db),
) -> TableResponse:
    """Historial de voto de un congresista, más reciente primero."""

    tabla = sql_tools.historial_congresista(
        session, nombre, legislatura=legislatura, limit=limit
    )
    return TableResponse(**tabla.model_dump())
