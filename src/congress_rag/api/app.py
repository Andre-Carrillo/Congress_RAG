"""Aplicación FastAPI que expone el corpus y la cadena RAG por HTTP."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from congress_rag import __version__
from congress_rag.api.routes import (
    busqueda,
    calidad,
    congresistas,
    consulta,
    meta,
    votaciones,
)
from congress_rag.api.schemas import EstadoSalud
from congress_rag.config import settings
from congress_rag.db.models import Documento, Votacion, Voto
from congress_rag.db.session import get_engine
from congress_rag.indexing.vector_store import ChromaStore

DESCRIPCION = """
API del prototipo **Congress_RAG** para consultar actas de votación del Congreso
del Perú (legislaturas 2025-2026-L1 y 2025-2026-L2).

- La recuperación (SQL + pasajes de las actas) funciona sin LLM.
- `/v1/buscar` expone el retrieval puro: pasajes literales con acta, página y similitud.
- Las cifras salen de consultas SQL deterministas, nunca del LLM.
- El LLM, si se activa, solo reformula la respuesta base y se valida después.
- Toda respuesta incluye acta, página y enlace al PDF cuando corresponde.
- Si el corpus no cubre la pregunta, la respuesta lo declara explícitamente.
- Los endpoints son de solo lectura, salvo `/v1/consulta`, que no escribe datos.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Congress_RAG API",
        description=DESCRIPCION,
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    origenes = settings.api_cors_origins_list
    if origenes:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origenes,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    app.include_router(consulta.router, prefix="/v1")
    app.include_router(busqueda.router, prefix="/v1")
    app.include_router(votaciones.router, prefix="/v1")
    app.include_router(congresistas.router, prefix="/v1")
    app.include_router(meta.router, prefix="/v1")
    app.include_router(calidad.router, prefix="/v1")

    @app.get("/health", response_model=EstadoSalud, tags=["estado"])
    def health() -> EstadoSalud:
        """Estado del servicio: base ingestada, índice vectorial y conteos.

        Cuando el índice está disponible, ``conteos`` incluye también
        ``chunks_narrativa`` y ``chunks_votaciones``.
        """

        if not settings.db_path.exists():
            return EstadoSalud(
                status="degraded",
                version=__version__,
                base_de_datos="ausente",
                indice_vectorial="no_disponible",
                detalle=(
                    "Falta data/processed/congress.db. Ejecuta `uv run python scripts/ingest.py`."
                ),
            )

        conteos: dict[str, int] = {}
        try:
            with Session(get_engine(settings.db_path)) as session:
                conteos = {
                    "actas": int(session.scalar(select(func.count()).select_from(Documento)) or 0),
                    "votaciones": int(
                        session.scalar(select(func.count()).select_from(Votacion)) or 0
                    ),
                    "votos": int(session.scalar(select(func.count()).select_from(Voto)) or 0),
                }
        except Exception as exc:  # pragma: no cover - base corrupta o bloqueada
            return EstadoSalud(
                status="degraded",
                version=__version__,
                base_de_datos="ausente",
                indice_vectorial="no_disponible",
                detalle=f"No se pudo leer la base: {exc}",
            )

        indice = (
            "disponible"
            if settings.chroma_dir.exists() and any(settings.chroma_dir.iterdir())
            else "no_disponible"
        )
        if indice == "disponible":
            for nombre in ("narrativa", "votaciones"):
                try:
                    conteos[f"chunks_{nombre}"] = ChromaStore(collection=nombre).count()
                except Exception:
                    continue
        return EstadoSalud(
            status="ok",
            version=__version__,
            base_de_datos="lista",
            indice_vectorial=indice,
            conteos=conteos,
        )

    @app.get("/", include_in_schema=False)
    def raiz() -> dict[str, str]:
        return {
            "servicio": "Congress_RAG API",
            "version": __version__,
            "documentacion": "/docs",
            "salud": "/health",
        }

    return app


app = create_app()
