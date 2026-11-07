"""Página principal de Congress_RAG."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select

from congress_rag.config import settings
from congress_rag.db.models import Documento, Votacion, Voto
from congress_rag.ui.common import db_exists, open_session

st.set_page_config(page_title="Congress_RAG", page_icon="🏛️", layout="wide")

st.title("Congress_RAG")
st.caption(
    "Sistema RAG híbrido para consultar actas de votación del Congreso del Perú "
    "con cifras exactas y fuentes citadas."
)

if not db_exists():
    st.warning(
        "La base de datos no existe todavía. Ve a **Ingesta** y ejecuta la carga "
        "del corpus, o corre `uv run python scripts/ingest.py`."
    )
else:
    with open_session() as session:
        documentos = session.scalar(select(func.count()).select_from(Documento)) or 0
        votaciones = session.scalar(select(func.count()).select_from(Votacion)) or 0
        votos = session.scalar(select(func.count()).select_from(Voto)) or 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Actas", documentos)
    col2.metric("Votaciones", votaciones)
    col3.metric("Votos registrados", f"{votos:,}")

    if settings.qa_report_path.exists():
        import pandas as pd

        qa = pd.read_csv(settings.qa_report_path, encoding="utf-8-sig")
        verificado = (
            int(qa["estado"].isin({"ok", "recuperado_subsanacion"}).sum())
            if "estado" in qa.columns
            else 0
        )
        st.metric("Votaciones verificadas", f"{verificado}/{len(qa)}")

st.divider()

st.subheader("Cómo funciona")
st.markdown(
    """
1. **Capa estructurada (SQLite):** responde conteos y listas exactas.
2. **Capa semántica (ChromaDB):** recupera el contexto del debate.
3. **Router:** decide qué capa usar según la pregunta.
4. **LLM:** redacta, pero **nunca calcula** los números.
5. **Exportación:** Excel y Word generados desde la tabla exacta.
"""
)

st.subheader("Estado del entorno")
st.code(
    f"Corpus: {settings.ushnu_dir}\n"
    f"Base:   {settings.db_path}\n"
    f"Chroma: {settings.chroma_dir}\n"
    f"Alcance: {', '.join(settings.legislaturas_list)}\n"
    f"Embeddings instalados: {importlib.util.find_spec('sentence_transformers') is not None}\n"
    f"Chroma instalado: {importlib.util.find_spec('chromadb') is not None}\n"
    f"Streamlit instalado: {importlib.util.find_spec('streamlit') is not None}",
    language="text",
)
