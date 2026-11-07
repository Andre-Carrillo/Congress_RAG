"""Pruebas de las consultas SQL deterministas."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from congress_rag.db.models import Base, Congresista, Documento, Legislatura, Votacion, Voto
from congress_rag.ingestion.normalize import normalize_key
from congress_rag.rag import sql_tools
from congress_rag.schemas import Filtros


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(Legislatura(id="2025-2026-L2", periodo_anual="2025-2026", nombre="Segunda"))
        session.add(Legislatura(id="2025-2026-L1", periodo_anual="2025-2026", nombre="Primera"))
        session.flush()

        session.add(
            Documento(
                acta_id="2026-03-05-01",
                fecha="2026-03-05",
                legislatura_id="2025-2026-L2",
                n_paginas=10,
                pdf_url="https://example.com/acta.pdf",
            )
        )
        session.add(
            Documento(
                acta_id="2025-12-03-29",
                fecha="2025-12-03",
                legislatura_id="2025-2026-L1",
                n_paginas=12,
            )
        )
        session.flush()

        documentos = {doc.acta_id: doc for doc in session.query(Documento).all()}
        session.add(
            Votacion(
                votacion_id="2026-03-05-01-v001",
                documento_id=documentos["2026-03-05-01"].id,
                indice_votacion=1,
                pagina_inicio=8,
                titulo="MOCIÓN 1486",
                titulo_normalizado=normalize_key("MOCIÓN 1486"),
                tipo="moción",
                conteo_si=2,
                conteo_no=1,
                conteo_abstencion=1,
            )
        )
        session.add(
            Votacion(
                votacion_id="2025-12-03-29-v001",
                documento_id=documentos["2025-12-03-29"].id,
                indice_votacion=1,
                pagina_inicio=3,
                titulo="PROYECTO 297",
                titulo_normalizado=normalize_key("PROYECTO 297"),
                tipo="proyecto",
                conteo_si=1,
                conteo_no=0,
                conteo_abstencion=0,
            )
        )
        session.flush()

        congresistas = [
            ("C1", "Ana Torres", "Fuerza Popular"),
            ("C2", "Luis Vega", "Fuerza Popular"),
            ("C3", "Eva Rojas", "Perú Libre"),
            ("C4", "Pedro Paz", "Perú Libre"),
        ]
        for congresista_id, nombre, bancada in congresistas:
            session.add(
                Congresista(
                    congresista_id=congresista_id,
                    nombre=nombre,
                    nombre_normalizado=normalize_key(nombre),
                    bancada=bancada,
                )
            )
        session.flush()

        ids = {c.congresista_id: c.id for c in session.query(Congresista).all()}
        votaciones = {v.votacion_id: v.id for v in session.query(Votacion).all()}
        v1 = "2026-03-05-01-v001"
        v2 = "2025-12-03-29-v001"

        session.add_all(
            [
                Voto(votacion_id=votaciones[v1], congresista_id=ids["C1"], posicion=1),
                Voto(votacion_id=votaciones[v1], congresista_id=ids["C2"], posicion=1),
                Voto(votacion_id=votaciones[v1], congresista_id=ids["C3"], posicion=-1),
                Voto(votacion_id=votaciones[v1], congresista_id=ids["C4"], posicion=0),
                Voto(votacion_id=votaciones[v2], congresista_id=ids["C1"], posicion=1),
                Voto(votacion_id=votaciones[v2], congresista_id=ids["C2"], posicion=1),
                Voto(votacion_id=votaciones[v2], congresista_id=ids["C3"], posicion=1),
                Voto(votacion_id=votaciones[v2], congresista_id=ids["C4"], posicion=1),
            ]
        )
        session.commit()
        yield session


def test_listar_votaciones_ordena_por_fecha(session: Session) -> None:
    filas = sql_tools.listar_votaciones(session)
    assert [fila["votacion_id"] for fila in filas] == [
        "2026-03-05-01-v001",
        "2025-12-03-29-v001",
    ]


def test_listar_votaciones_filtra_legislatura(session: Session) -> None:
    filas = sql_tools.listar_votaciones(
        session, filtros=Filtros(legislatura="2025-2026-L1")
    )
    assert [fila["votacion_id"] for fila in filas] == ["2025-12-03-29-v001"]


def test_listar_votaciones_busca_por_titulo_normalizado(session: Session) -> None:
    filas = sql_tools.listar_votaciones(session, texto="mocion 1486")
    assert [fila["votacion_id"] for fila in filas] == ["2026-03-05-01-v001"]


def test_obtener_votacion(session: Session) -> None:
    fila = sql_tools.obtener_votacion(session, "2025-12-03-29-v001")
    assert fila is not None
    assert fila["titulo"] == "PROYECTO 297"
    assert fila["acta_id"] == "2025-12-03-29"
    assert sql_tools.obtener_votacion(session, "no-existe") is None


def test_conteo_por_bancada(session: Session) -> None:
    tabla = sql_tools.conteo_por_bancada(session, "2026-03-05-01-v001")
    assert tabla.columnas == ["Bancada", "A favor", "En contra", "Abstención", "Total"]
    assert tabla.filas[0] == ["Fuerza Popular", 2, 0, 0, 2]
    assert tabla.filas[1] == ["Perú Libre", 0, 1, 1, 2]


def test_lista_votos_favor(session: Session) -> None:
    tabla = sql_tools.lista_votos(session, "2026-03-05-01-v001", 1)
    assert [fila[0] for fila in tabla.filas] == ["Ana Torres", "Luis Vega"]


def test_historial_congresista(session: Session) -> None:
    tabla = sql_tools.historial_congresista(session, "Ana Torres")
    assert len(tabla.filas) == 2
    assert all(fila[0] == "Ana Torres" for fila in tabla.filas)
    assert tabla.filas[0][5] == "MOCIÓN 1486"
    assert tabla.filas[0][6] == "2026-03-05-01-v001"


def test_historial_congresista_filtra_legislatura(session: Session) -> None:
    tabla = sql_tools.historial_congresista(
        session, "Ana Torres", legislatura="2025-2026-L1"
    )
    assert len(tabla.filas) == 1
    assert tabla.filas[0][4] == "2025-2026-L1"


def test_ausencias_por_votacion_deriva_complemento(session: Session) -> None:
    documento = session.query(Documento).filter_by(acta_id="2026-03-05-01").one()
    session.add(
        Congresista(
            congresista_id="C5",
            nombre="Rosa Lima",
            nombre_normalizado=normalize_key("Rosa Lima"),
            bancada="Perú Libre",
        )
    )
    session.flush()
    otra = Votacion(
        votacion_id="2026-03-05-01-v002",
        documento_id=documento.id,
        titulo="OTRA VOTACIÓN",
        titulo_normalizado=normalize_key("OTRA VOTACIÓN"),
        tipo="otro",
    )
    session.add(otra)
    session.flush()
    rosa = session.query(Congresista).filter_by(congresista_id="C5").one()
    session.add(Voto(votacion_id=otra.id, congresista_id=rosa.id, posicion=1))
    session.commit()

    tabla = sql_tools.ausencias_por_votacion(session, "2026-03-05-01-v001")
    assert tabla.metadata["derivado"] is True
    assert [fila[0] for fila in tabla.filas] == ["Rosa Lima"]


def test_votaciones_por_tipo(session: Session) -> None:
    tabla = sql_tools.votaciones_por_tipo(session, "moción")
    assert len(tabla.filas) == 1
    assert tabla.filas[0][0] == "2026-03-05-01-v001"
