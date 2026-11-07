"""Orquestación de la ingesta completa."""

from __future__ import annotations

from congress_rag.config import Settings, settings
from congress_rag.db.session import get_engine, get_session
from congress_rag.ingestion.bootstrap import (
    bootstrap,
    cargar_legacy,
    construir_reporte_calidad,
)
from congress_rag.ingestion.chunker import construir_chunks
from congress_rag.schemas import IngestStats


def run_ingest(
    cfg: Settings | None = None,
    *,
    build_chunks: bool = True,
    verbose: bool = True,
) -> IngestStats:
    cfg = cfg or settings
    engine = get_engine(cfg.db_path)

    with get_session(engine) as session:
        stats = bootstrap(session, cfg)
        legacy = cargar_legacy(cfg.legacy_dir, cfg.legislaturas_list)
        qa = construir_reporte_calidad(session, legacy, cfg)
        stats.qa_total = len(qa)
        stats.qa_ok = (
            int(qa["estado"].isin({"ok", "recuperado_subsanacion"}).sum())
            if not qa.empty
            else 0
        )
        if build_chunks:
            stats.chunks = construir_chunks(session, cfg)

    if verbose:
        print(resumen_texto(stats))
    return stats


def run_chunks_only(cfg: Settings | None = None, *, verbose: bool = True) -> int:
    cfg = cfg or settings
    engine = get_engine(cfg.db_path)
    with get_session(engine) as session:
        total = construir_chunks(session, cfg)
    if verbose:
        print(f"Chunks generados: {total} -> {cfg.chunks_path}")
    return total


def resumen_texto(stats: IngestStats) -> str:
    pct = (stats.qa_ok / stats.qa_total * 100) if stats.qa_total else 0.0
    return (
        "Ingesta completada\n"
        f"  Documentos:   {stats.documentos}\n"
        f"  Congresistas: {stats.congresistas}\n"
        f"  Votaciones:   {stats.votaciones}\n"
        f"  Votos:        {stats.votos}\n"
        f"  Chunks:       {stats.chunks}\n"
        f"  QA:           {stats.qa_ok}/{stats.qa_total} OK ({pct:.1f}%)"
    )
