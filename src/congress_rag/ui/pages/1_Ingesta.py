"""Página de ingesta del corpus."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from congress_rag.config import settings
from congress_rag.ingestion.pipeline import run_ingest

st.set_page_config(page_title="Ingesta · Congress_RAG", page_icon="📥", layout="wide")
st.title("Ingesta del corpus")

st.markdown(
    f"**Fuente:** `{settings.ushnu_dir}`  \n"
    f"**Alcance:** `{', '.join(settings.legislaturas_list)}`  \n"
    f"**Base de datos:** `{settings.db_path}`"
)

st.info(
    "La ingesta es idempotente: reconstruye la base y vuelve a generar "
    "`qa_report.csv` y `chunks.jsonl`. No descarga PDFs ni ejecuta el scraper."
)

if st.button("Ejecutar ingesta", type="primary"):
    with st.spinner("Cargando corpus, calculando QA y generando chunks..."):
        try:
            stats = run_ingest(verbose=False)
        except Exception as exc:
            st.error(f"Error en la ingesta: {exc}")
        else:
            st.success("Ingesta completada")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Actas", stats.documentos)
            col2.metric("Votaciones", stats.votaciones)
            col3.metric("Votos", f"{stats.votos:,}")
            col4.metric("Chunks", f"{stats.chunks:,}")
            if stats.qa_total:
                st.metric(
                    "QA OK",
                    f"{stats.qa_ok}/{stats.qa_total} "
                    f"({stats.qa_ok / stats.qa_total * 100:.1f}%)",
                )

st.divider()
st.subheader("Reporte de calidad")

if settings.qa_report_path.exists():
    qa = pd.read_csv(settings.qa_report_path, encoding="utf-8-sig")
    col1, col2, col3 = st.columns(3)
    col1.metric("Votaciones", len(qa))
    if "estado" in qa.columns:
        verificado = int(
            qa["estado"].isin({"ok", "recuperado_subsanacion"}).sum()
        )
        col2.metric("Integridad verificada", verificado)
        col3.metric("Requieren revisión", len(qa) - verificado)
        st.dataframe(
            qa["estado"].value_counts().rename_axis("Estado").reset_index(name="Votaciones"),
            use_container_width=True,
            hide_index=True,
        )

    if "estado" in qa.columns:
        estados = st.multiselect(
            "Filtrar por estado",
            options=sorted(qa["estado"].dropna().unique().tolist()),
            default=sorted(qa["estado"].dropna().unique().tolist()),
        )
        qa = qa[qa["estado"].isin(estados)]

    st.dataframe(qa, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar qa_report.csv",
        data=settings.qa_report_path.read_bytes(),
        file_name="qa_report.csv",
        mime="text/csv",
    )
else:
    st.info("Aún no existe `qa_report.csv`. Ejecuta la ingesta.")
