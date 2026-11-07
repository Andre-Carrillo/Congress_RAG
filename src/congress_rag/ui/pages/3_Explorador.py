"""Explorador de votaciones y votos con filtros deterministas."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from congress_rag.rag import sql_tools
from congress_rag.schemas import Filtros
from congress_rag.ui.common import db_exists, open_session

st.set_page_config(page_title="Explorador · Congress_RAG", page_icon="🔎", layout="wide")
st.title("Explorador de votaciones")

if not db_exists():
    st.warning("Primero ejecuta la ingesta.")
    st.stop()

with open_session() as session:
    legislaturas = [
        fila[0]
        for fila in session.execute(
            text("SELECT DISTINCT legislatura_id FROM documentos ORDER BY legislatura_id")
        ).all()
    ]
    tipos = [
        fila[0]
        for fila in session.execute(
            text("SELECT DISTINCT tipo FROM votaciones WHERE tipo IS NOT NULL ORDER BY tipo")
        ).all()
    ]

col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    legislatura = st.selectbox("Legislatura", ["Todas", *legislaturas])
with col2:
    tipo = st.selectbox("Tipo", ["Todos", *tipos])
with col3:
    texto = st.text_input("Buscar en el título", placeholder="moción 21506, proyecto 186...")

filtros = Filtros(
    legislatura=None if legislatura == "Todas" else legislatura,
    tipo=None if tipo == "Todos" else tipo,
)

with open_session() as session:
    filas = sql_tools.listar_votaciones(
        session, filtros=filtros, texto=texto or None, limit=500
    )

st.caption(f"{len(filas)} votaciones encontradas (máximo 500)")

if not filas:
    st.info("No hay votaciones que coincidan con los filtros.")
    st.stop()

tabla = pd.DataFrame(filas)
tabla = tabla.rename(
    columns={
        "votacion_id": "ID",
        "titulo": "Título",
        "tipo": "Tipo",
        "pagina_inicio": "Página",
        "conteo_si": "Sí",
        "conteo_no": "No",
        "conteo_abstencion": "Abst.",
        "acta_id": "Acta",
        "fecha": "Fecha",
        "legislatura_id": "Legislatura",
        "pdf_url": "PDF",
    }
)

st.dataframe(
    tabla,
    use_container_width=True,
    hide_index=True,
    column_config={
        "PDF": st.column_config.LinkColumn("PDF", display_text="Abrir"),
    },
)

st.divider()
st.subheader("Detalle de una votación")

seleccion = st.selectbox(
    "Votación",
    options=[fila["votacion_id"] for fila in filas],
    format_func=lambda valor: next(
        (fila["titulo"][:120] for fila in filas if fila["votacion_id"] == valor), valor
    ),
)

if seleccion:
    with open_session() as session:
        detalle = sql_tools.obtener_votacion(session, seleccion)
        por_bancada = sql_tools.conteo_por_bancada(session, seleccion)

    if detalle:
        st.markdown(f"**{detalle['titulo']}**")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("A favor", detalle["conteo_si"])
        col2.metric("En contra", detalle["conteo_no"])
        col3.metric("Abstención", detalle["conteo_abstencion"])
        col4.metric("Acta · página", f"{detalle['acta_id']} · {detalle['pagina_inicio']}")
        if detalle.get("pdf_url"):
            st.markdown(f"[Abrir PDF del acta]({detalle['pdf_url']})")

    if por_bancada.filas:
        st.markdown(f"**{por_bancada.titulo}**")
        st.dataframe(
            pd.DataFrame(por_bancada.filas, columns=por_bancada.columnas),
            use_container_width=True,
            hide_index=True,
        )

    posiciones = {
        "A favor": 1,
        "En contra": -1,
        "Abstención": 0,
        "No votó (derivado)": 2,
    }
    posicion_label = st.radio("Listar votos", list(posiciones), horizontal=True)
    posicion = posiciones[posicion_label]

    with open_session() as session:
        if posicion == 2:
            votos = sql_tools.ausencias_por_votacion(session, seleccion)
        else:
            votos = sql_tools.lista_votos(session, seleccion, posicion)

    if votos.filas:
        st.dataframe(
            pd.DataFrame(votos.filas, columns=votos.columnas),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No hay registros para esa posición.")
