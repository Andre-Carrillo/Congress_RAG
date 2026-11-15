"""Endpoint de consulta en lenguaje natural y exportación del resultado."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from congress_rag.api.deps import get_db, get_retriever, resolver_llm
from congress_rag.api.schemas import ConsultaRequest, ConsultaResponse
from congress_rag.export.excel import to_excel
from congress_rag.export.word import to_word
from congress_rag.rag.chain import answer_question

router = APIRouter(prefix="/consulta", tags=["consulta"])

MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _responder(session: Session, payload: ConsultaRequest) -> ConsultaResponse:
    provider, advertencias = resolver_llm(payload.usar_llm)
    answer = answer_question(
        session,
        payload.pregunta,
        provider=provider,
        retriever=get_retriever(),
        use_llm=payload.usar_llm,
    )
    answer.advertencias.extend(advertencias)
    return ConsultaResponse(**answer.model_dump())


@router.post("", response_model=ConsultaResponse)
def consultar(
    payload: ConsultaRequest,
    session: Session = Depends(get_db),
) -> ConsultaResponse:
    """Responde una pregunta con cifras exactas, tabla y citas.

    El router decide entre SQL y recuperación semántica; el LLM solo redacta.
    Nunca calcula números y, si no hay evidencia, la respuesta lo declara.
    """

    return _responder(session, payload)


@router.post("/export")
def exportar(
    payload: ConsultaRequest,
    formato: Literal["excel", "word"] = Query("excel", description="Formato de salida"),
    session: Session = Depends(get_db),
) -> Response:
    """Genera la misma respuesta y la devuelve como archivo Excel o Word."""

    answer = _responder(session, payload)
    if formato == "word":
        contenido = to_word(answer)
        media_type = MIME_WORD
        nombre = "congress_rag_consulta.docx"
    else:
        contenido = to_excel(answer)
        media_type = MIME_EXCEL
        nombre = "congress_rag_consulta.xlsx"

    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
