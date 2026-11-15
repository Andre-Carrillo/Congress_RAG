"""Endpoints de transparencia: cobertura del corpus y reporte de calidad."""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from congress_rag.api.deps import get_db
from congress_rag.api.schemas import PaginaQa, ResumenCalidad
from congress_rag.config import settings
from congress_rag.rag import sql_tools

router = APIRouter(prefix="/calidad", tags=["calidad"])


@router.get("/resumen", response_model=ResumenCalidad)
def resumen(session: Session = Depends(get_db)) -> ResumenCalidad:
    """Conteos del corpus, confianza de extracción y estado del QA."""

    datos: dict[str, Any] = sql_tools.resumen_calidad(session)
    datos["qa"] = _resumen_qa()
    return ResumenCalidad(**datos)


@router.get("/qa", response_model=PaginaQa)
def reporte_qa(
    estado: str | None = Query(None, description="Ej. ok, discrepancia_conteo, sin_votos"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> PaginaQa:
    """Filas del ``qa_report.csv`` generado por la ingesta."""

    if not settings.qa_report_path.exists():
        return PaginaQa(total=0, items=[])

    tabla = pd.read_csv(settings.qa_report_path, encoding="utf-8-sig")
    if estado and "estado" in tabla.columns:
        tabla = tabla[tabla["estado"] == estado]
    pagina = tabla.iloc[offset : offset + limit].fillna("").to_dict(orient="records")
    return PaginaQa(total=len(tabla), items=pagina)


def _resumen_qa() -> dict[str, Any]:
    if not settings.qa_report_path.exists():
        return {"disponible": False}

    qa = pd.read_csv(settings.qa_report_path, encoding="utf-8-sig")
    resumen: dict[str, Any] = {"disponible": True, "total": len(qa)}
    if "estado" in qa.columns:
        resumen["por_estado"] = {
            str(estado): int(cantidad)
            for estado, cantidad in qa["estado"].value_counts().items()
        }
        resumen["ok"] = int((qa["estado"] == "ok").sum())
        verificadas = int(
            qa["estado"].isin(["ok", "recuperado_subsanacion"]).sum()
        )
        resumen["integridad_verificada"] = verificadas
        resumen["porcentaje_verificado"] = round(verificadas / len(qa) * 100, 1)
    if "legacy_encontrado" in qa.columns:
        resumen["legacy_encontrado"] = int(qa["legacy_encontrado"].sum())
    return resumen
