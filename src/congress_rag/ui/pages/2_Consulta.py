"""Página de consulta en lenguaje natural."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from congress_rag.config import settings
from congress_rag.export.excel import to_excel
from congress_rag.export.word import to_word
from congress_rag.rag.chain import answer_question
from congress_rag.rag.llm import get_provider
from congress_rag.rag.retriever import Retriever
from congress_rag.ui.common import db_exists, open_session

st.set_page_config(page_title="Consulta · Congress_RAG", page_icon="💬", layout="wide")
st.title("Consulta en lenguaje natural")

if not db_exists():
    st.warning("Primero ejecuta la ingesta.")
    st.stop()

with st.sidebar:
    st.subheader("Opciones")
    usar_llm = st.checkbox(
        "Usar LLM (Ollama/Gemini)",
        value=True,
        help="Si se desactiva, la respuesta se genera de forma determinista desde SQL.",
    )
    st.caption(f"Proveedor configurado: `{settings.llm_provider}`")
    st.caption(f"Embeddings: `{settings.embedding_model}`")

pregunta = st.text_input(
    "Pregunta",
    placeholder="¿Cómo votó cada bancada en la moción 19785?",
)

if st.button("Consultar", type="primary") and pregunta.strip():
    provider = None
    advertencia_provider = None
    if usar_llm:
        try:
            provider = get_provider()
        except Exception as exc:
            advertencia_provider = str(exc)

    retriever = None
    try:
        retriever = Retriever()
    except Exception:
        retriever = None

    with open_session() as session:
        try:
            answer = answer_question(
                session,
                pregunta,
                provider=provider,
                retriever=retriever,
                use_llm=usar_llm,
            )
        except Exception as exc:
            st.error(f"Error al responder: {exc}")
        else:
            st.session_state["answer"] = answer
            if advertencia_provider:
                st.warning(f"LLM no disponible: {advertencia_provider}")

if "answer" in st.session_state:
    answer = st.session_state["answer"]

    st.subheader("Respuesta")
    st.write(answer.respuesta)
    st.caption(f"Confianza: **{answer.confianza}**")

    for advertencia in answer.advertencias:
        st.warning(advertencia)

    if answer.tabla and answer.tabla.filas:
        st.subheader(answer.tabla.titulo)
        st.dataframe(
            pd.DataFrame(answer.tabla.filas, columns=answer.tabla.columnas),
            use_container_width=True,
            hide_index=True,
        )

    if answer.fuentes:
        with st.expander("Fuentes", expanded=True):
            for fuente in answer.fuentes:
                texto = f"Acta **{fuente.acta_id}**"
                if fuente.pagina:
                    texto += f" · página {fuente.pagina}"
                if fuente.votacion_id:
                    texto += f" · `{fuente.votacion_id}`"
                if fuente.pdf_url:
                    texto += f" · [ver PDF]({fuente.pdf_url})"
                st.markdown(f"- {texto}")

    col1, col2 = st.columns(2)
    col1.download_button(
        "Exportar a Excel",
        data=to_excel(answer),
        file_name="congress_rag_respuesta.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    col2.download_button(
        "Exportar a Word",
        data=to_word(answer),
        file_name="congress_rag_respuesta.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
