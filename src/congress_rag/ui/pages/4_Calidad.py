"""Página de calidad de datos: cobertura, confianza y discrepancias."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from congress_rag.config import settings
from congress_rag.db.models import Documento, Votacion, Voto
from congress_rag.ui.common import db_exists, open_session

st.set_page_config(page_title="Calidad · Congress_RAG", page_icon="📊", layout="wide")
st.title("Calidad del corpus")

st.markdown(
    "Esta página **no oculta** las limitaciones: muestra qué se recuperó, "
    "qué tan confiable es y qué discrepa respecto de la fuente anterior."
)

if not db_exists():
    st.warning("Primero ejecuta la ingesta.")
    st.stop()

with open_session() as session:
    documentos = session.scalar(select(func.count()).select_from(Documento)) or 0
    votaciones = session.scalar(select(func.count()).select_from(Votacion)) or 0
    votos = session.scalar(select(func.count()).select_from(Voto)) or 0
    paginas = session.scalar(select(func.sum(Documento.n_paginas))) or 0

    confianza = dict(
        session.execute(
            select(Voto.confianza, func.count()).group_by(Voto.confianza)
        ).all()
    )

col1, col2, col3, col4 = st.columns(4)
col1.metric("Actas", documentos)
col2.metric("Votaciones", votaciones)
col3.metric("Votos registrados", f"{votos:,}")
col4.metric("Páginas procesadas", f"{int(paginas):,}")

st.divider()
st.subheader("Confianza de extracción por voto")

if confianza:
    total = sum(confianza.values()) or 1
    tabla_confianza = pd.DataFrame(
        [
            {
                "Confianza": (clave or "sin dato").capitalize(),
                "Votos": cantidad,
                "Porcentaje": round(cantidad / total * 100, 2),
            }
            for clave, cantidad in sorted(confianza.items(), key=lambda item: -item[1])
        ]
    )
    col1, col2 = st.columns([2, 3])
    with col1:
        st.dataframe(tabla_confianza, use_container_width=True, hide_index=True)
    with col2:
        st.bar_chart(
            tabla_confianza.set_index("Confianza")["Porcentaje"], horizontal=True
        )

    alta = confianza.get("alta", 0)
    st.caption(
        f"Los votos de confianza **alta** son {alta:,} de {total:,} "
        f"({alta / total * 100:.1f}%). El resto proviene de listas narrativas "
        "y debe interpretarse con cautela."
    )

st.divider()
st.subheader("Reporte de calidad (QA)")

if not settings.qa_report_path.exists():
    st.info("Aún no existe `qa_report.csv`. Ejecuta la ingesta.")
    st.stop()

qa = pd.read_csv(settings.qa_report_path, encoding="utf-8-sig")

col1, col2, col3 = st.columns(3)
col1.metric("Votaciones evaluadas", len(qa))
if "estado" in qa.columns:
    ok = int((qa["estado"] == "ok").sum())
    col2.metric("Estado OK", ok)
    col3.metric("Requieren revisión", len(qa) - ok)

    estados = sorted(qa["estado"].dropna().unique().tolist())
    seleccion = st.multiselect("Filtrar por estado", estados, default=estados)
    filtrado = qa[qa["estado"].isin(seleccion)]
else:
    filtrado = qa

st.dataframe(filtrado, use_container_width=True, hide_index=True)
st.download_button(
    "Descargar qa_report.csv",
    data=settings.qa_report_path.read_bytes(),
    file_name="qa_report.csv",
    mime="text/csv",
)

if "legacy_encontrado" in qa.columns:
    st.divider()
    st.subheader("Comparación con el corpus anterior")
    encontradas = int(qa["legacy_encontrado"].sum())
    st.markdown(
        f"- Votaciones con equivalente en `votos_csv`: **{encontradas}** de {len(qa)}.\n"
        f"- Votaciones recuperadas solo por `ushnu-congreso`: **{len(qa) - encontradas}**.\n"
        "- Las discrepancias de conteo se listan arriba con estado "
        "`discrepancia_conteo` o `discrepancia_legacy`."
    )
