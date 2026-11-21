"""Modelos de entrada y salida de la API HTTP."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from congress_rag.schemas import Answer, TableSpec


class ConsultaRequest(BaseModel):
    pregunta: str = Field(
        min_length=3,
        max_length=500,
        description="Pregunta en lenguaje natural sobre las actas de votación.",
        examples=["¿Cómo votó cada bancada en la moción 19785?"],
    )
    usar_llm: bool = Field(
        default=True,
        description=(
            "Redacta la respuesta con el LLM configurado. Si el proveedor no está "
            "disponible, la API responde de forma determinista y lo advierte."
        ),
    )


class ConsultaResponse(Answer):
    """Respuesta con cifras deterministas, tabla opcional y fuentes citadas."""


class VotacionResumen(BaseModel):
    votacion_id: str
    titulo: str
    tipo: str | None = None
    pagina_inicio: int | None = None
    conteo_si: int
    conteo_no: int
    conteo_abstencion: int
    acta_id: str
    fecha: str | None = None
    legislatura_id: str
    pdf_url: str | None = None


class PaginaVotaciones(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[VotacionResumen]


class ActaResumen(BaseModel):
    acta_id: str
    numero_sesion: int | None = None
    fecha: str | None = None
    legislatura_id: str
    n_paginas: int | None = None
    pdf_url: str | None = None
    votaciones: int


class PaginaActas(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ActaResumen]


class LegislaturaResumen(BaseModel):
    id: str
    periodo_anual: str
    nombre: str
    actas: int
    votaciones: int


class BancadaResumen(BaseModel):
    bancada: str
    congresistas: int


class CongresistaResumen(BaseModel):
    congresista_id: str
    nombre: str
    bancada: str | None = None
    grupo_partido: str | None = None
    perfil_url: str | None = None


class ResultadoBusqueda(BaseModel):
    """Pasaje recuperado por similitud semántica, sin redacción."""

    acta_id: str
    pagina: int | None = None
    score: float
    texto: str
    votacion_id: str | None = None
    pdf_url: str | None = None


class RespuestaBusqueda(BaseModel):
    """Resultado del retrieval puro; no interviene ningún LLM."""

    consulta: str
    coleccion: Literal["narrativa", "votaciones"]
    total: int
    resultados: list[ResultadoBusqueda] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class TableResponse(TableSpec):
    """Tabla reproducible equivalente a la que muestra la interfaz."""


class EstadoSalud(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    base_de_datos: Literal["lista", "ausente"]
    indice_vectorial: Literal["disponible", "no_disponible"]
    detalle: str | None = None
    conteos: dict[str, int] = Field(default_factory=dict)


class ResumenCalidad(BaseModel):
    actas: int
    votaciones: int
    votos: int
    congresistas: int
    paginas: int
    confianza_votos: dict[str, int]
    qa: dict[str, Any] = Field(default_factory=dict)


class PaginaQa(BaseModel):
    total: int
    items: list[dict[str, Any]]
