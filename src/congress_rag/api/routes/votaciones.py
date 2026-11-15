"""Endpoints de votaciones y de la composición del voto."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from congress_rag.api.deps import get_db
from congress_rag.api.schemas import PaginaVotaciones, TableResponse, VotacionResumen
from congress_rag.rag import sql_tools
from congress_rag.schemas import Filtros

router = APIRouter(prefix="/votaciones", tags=["votaciones"])

PosicionVoto = Literal["a_favor", "en_contra", "abstencion", "no_voto"]
POSICIONES = {"a_favor": 1, "en_contra": -1, "abstencion": 0, "no_voto": 2}


@router.get("", response_model=PaginaVotaciones)
def listar_votaciones(
    legislatura: str | None = Query(None, description="Ej. 2025-2026-L2"),
    tipo: str | None = Query(None, description="Tipo exacto, ver /v1/tipos"),
    acta_id: str | None = Query(None, description="Ej. 2026-03-05-01"),
    texto: str | None = Query(None, description="Búsqueda en el título: 'moción 19785'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> PaginaVotaciones:
    """Lista paginada de votaciones con filtros deterministas."""

    filtros = Filtros(legislatura=legislatura, tipo=tipo, acta_id=acta_id)
    filas = sql_tools.listar_votaciones(
        session, filtros=filtros, texto=texto, limit=limit, offset=offset
    )
    return PaginaVotaciones(
        total=sql_tools.contar_votaciones(session, filtros=filtros, texto=texto),
        limit=limit,
        offset=offset,
        items=[VotacionResumen(**fila) for fila in filas],
    )


@router.get("/{votacion_id}", response_model=VotacionResumen)
def obtener_votacion(
    votacion_id: str = Path(description="ID de votación, ej. 2026-03-05-01-v001"),
    session: Session = Depends(get_db),
) -> VotacionResumen:
    """Detalle de una votación: título, conteos, acta y página."""

    fila = sql_tools.obtener_votacion(session, votacion_id)
    if not fila:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la votación {votacion_id}.",
        )
    return VotacionResumen(**fila)


@router.get("/{votacion_id}/bancadas", response_model=TableResponse)
def conteo_por_bancada(
    votacion_id: str,
    session: Session = Depends(get_db),
) -> TableResponse:
    """Conteo de votos por bancada para una votación."""

    _exigir_votacion(session, votacion_id)
    tabla = sql_tools.conteo_por_bancada(session, votacion_id)
    return TableResponse(**tabla.model_dump())


@router.get("/{votacion_id}/votos", response_model=TableResponse)
def listar_votos(
    votacion_id: str,
    posicion: PosicionVoto = Query("a_favor", description="Posición a listar"),
    session: Session = Depends(get_db),
) -> TableResponse:
    """Lista nominal de congresistas según su posición.

    ``no_voto`` se deriva por complemento: son los congresistas activos en la
    legislatura que no registran voto explícito en esa votación.
    """

    _exigir_votacion(session, votacion_id)
    if posicion == "no_voto":
        tabla = sql_tools.ausencias_por_votacion(session, votacion_id)
    else:
        tabla = sql_tools.lista_votos(session, votacion_id, POSICIONES[posicion])
    return TableResponse(**tabla.model_dump())


def _exigir_votacion(session: Session, votacion_id: str) -> None:
    if not sql_tools.obtener_votacion(session, votacion_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la votación {votacion_id}.",
        )
