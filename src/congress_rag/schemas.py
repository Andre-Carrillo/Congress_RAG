"""Modelos de dominio compartidos por ingesta, RAG y exportación."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Posicion(IntEnum):
    FAVOR = 1
    CONTRA = -1
    ABSTENCION = 0
    NO_VOTO = 2


POSICION_LABEL = {
    Posicion.FAVOR: "A favor",
    Posicion.CONTRA: "En contra",
    Posicion.ABSTENCION: "Abstención",
    Posicion.NO_VOTO: "No votó",
}


class TableSpec(BaseModel):
    """Resultado tabular reproducible que la UI puede mostrar y exportar."""

    titulo: str
    columnas: list[str]
    filas: list[list[Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class Fuente(BaseModel):
    acta_id: str
    pagina: int | None = None
    pdf_url: str | None = None
    votacion_id: str | None = None


class Answer(BaseModel):
    pregunta: str
    respuesta: str
    fuentes: list[Fuente] = Field(default_factory=list)
    tabla: TableSpec | None = None
    confianza: Literal["alta", "media", "baja"] = "media"
    advertencias: list[str] = Field(default_factory=list)


class Filtros(BaseModel):
    legislatura: str | None = None
    bancada: str | None = None
    congresista: str | None = None
    acta_id: str | None = None
    tipo: str | None = None
    proyecto_o_mocion: str | None = None


class QueryPlan(BaseModel):
    intencion: Literal["agregacion", "busqueda", "mixta", "fuera_de_alcance"]
    filtros: Filtros = Field(default_factory=Filtros)
    requiere_sql: bool = True
    requiere_contexto: bool = False
    consulta_reescrita: str = ""


class ParsedVotacion(BaseModel):
    titulo: str
    favor: list[str] = Field(default_factory=list)
    contra: list[str] = Field(default_factory=list)
    abstencion: list[str] = Field(default_factory=list)
    pagina: int = 1


class IngestStats(BaseModel):
    documentos: int = 0
    congresistas: int = 0
    votaciones: int = 0
    votos: int = 0
    chunks: int = 0
    qa_ok: int = 0
    qa_total: int = 0
