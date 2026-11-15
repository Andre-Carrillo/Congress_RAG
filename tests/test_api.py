"""Pruebas de los endpoints HTTP de la API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from congress_rag.api.app import create_app
from congress_rag.api.deps import get_db
from congress_rag.config import settings
from congress_rag.db.models import Base, Congresista, Documento, Legislatura, Votacion, Voto
from congress_rag.ingestion.normalize import normalize_key

V1 = "2026-03-05-01-v001"
V2 = "2025-12-03-29-v001"


def _poblar(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                Legislatura(
                    id="2025-2026-L2", periodo_anual="2025-2026", nombre="Segunda"
                ),
                Legislatura(
                    id="2025-2026-L1", periodo_anual="2025-2026", nombre="Primera"
                ),
            ]
        )
        session.flush()

        session.add_all(
            [
                Documento(
                    acta_id="2026-03-05-01",
                    fecha="2026-03-05",
                    legislatura_id="2025-2026-L2",
                    n_paginas=10,
                    pdf_url="https://example.com/acta.pdf",
                ),
                Documento(
                    acta_id="2025-12-03-29",
                    fecha="2025-12-03",
                    legislatura_id="2025-2026-L1",
                    n_paginas=12,
                ),
            ]
        )
        session.flush()

        documentos = {doc.acta_id: doc for doc in session.query(Documento).all()}
        session.add_all(
            [
                Votacion(
                    votacion_id=V1,
                    documento_id=documentos["2026-03-05-01"].id,
                    indice_votacion=1,
                    pagina_inicio=8,
                    titulo="MOCIÓN 1486",
                    titulo_normalizado=normalize_key("MOCIÓN 1486"),
                    tipo="moción",
                    conteo_si=2,
                    conteo_no=1,
                    conteo_abstencion=1,
                ),
                Votacion(
                    votacion_id=V2,
                    documento_id=documentos["2025-12-03-29"].id,
                    indice_votacion=1,
                    pagina_inicio=3,
                    titulo="PROYECTO 297",
                    titulo_normalizado=normalize_key("PROYECTO 297"),
                    tipo="proyecto",
                    conteo_si=4,
                ),
            ]
        )
        session.flush()

        for congresista_id, nombre, bancada in [
            ("C1", "Ana Torres", "Fuerza Popular"),
            ("C2", "Luis Vega", "Fuerza Popular"),
            ("C3", "Eva Rojas", "Perú Libre"),
            ("C4", "Pedro Paz", "Perú Libre"),
        ]:
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
        session.add_all(
            [
                Voto(
                    votacion_id=votaciones[V1],
                    congresista_id=ids["C1"],
                    posicion=1,
                    confianza="alta",
                ),
                Voto(
                    votacion_id=votaciones[V1],
                    congresista_id=ids["C2"],
                    posicion=1,
                    confianza="alta",
                ),
                Voto(
                    votacion_id=votaciones[V1],
                    congresista_id=ids["C3"],
                    posicion=-1,
                    confianza="media",
                ),
                Voto(
                    votacion_id=votaciones[V1],
                    congresista_id=ids["C4"],
                    posicion=0,
                    confianza="media",
                ),
                Voto(votacion_id=votaciones[V2], congresista_id=ids["C1"], posicion=1),
                Voto(votacion_id=votaciones[V2], congresista_id=ids["C2"], posicion=1),
                Voto(votacion_id=votaciones[V2], congresista_id=ids["C3"], posicion=1),
                Voto(votacion_id=votaciones[V2], congresista_id=ids["C4"], posicion=1),
            ]
        )
        session.commit()


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    ruta_db = tmp_path / "api.db"
    engine = create_engine(f"sqlite:///{ruta_db}", future=True)
    _poblar(engine)
    monkeypatch.setattr(settings, "db_path", ruta_db)

    app = create_app()

    def _sesion_prueba():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _sesion_prueba
    monkeypatch.setattr(
        "congress_rag.api.routes.consulta.get_retriever", lambda: None
    )
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def test_health_reporta_base_lista(client: TestClient) -> None:
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["base_de_datos"] == "lista"
    assert cuerpo["conteos"]["votaciones"] == 2


def test_raiz_anuncia_documentacion(client: TestClient) -> None:
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert respuesta.json()["documentacion"] == "/docs"


def test_listar_votaciones_pagina_y_filtra(client: TestClient) -> None:
    respuesta = client.get("/v1/votaciones")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 2
    assert [item["votacion_id"] for item in cuerpo["items"]] == [V1, V2]

    filtrado = client.get("/v1/votaciones", params={"legislatura": "2025-2026-L1"})
    assert filtrado.json()["total"] == 1
    assert filtrado.json()["items"][0]["votacion_id"] == V2

    paginado = client.get("/v1/votaciones", params={"limit": 1, "offset": 1})
    assert paginado.json()["total"] == 2
    assert len(paginado.json()["items"]) == 1


def test_listar_votaciones_busca_por_texto(client: TestClient) -> None:
    respuesta = client.get("/v1/votaciones", params={"texto": "moción 1486"})
    assert respuesta.status_code == 200
    assert [item["votacion_id"] for item in respuesta.json()["items"]] == [V1]


def test_detalle_de_votacion(client: TestClient) -> None:
    respuesta = client.get(f"/v1/votaciones/{V1}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["titulo"] == "MOCIÓN 1486"
    assert cuerpo["acta_id"] == "2026-03-05-01"

    assert client.get("/v1/votaciones/no-existe").status_code == 404


def test_conteo_por_bancada(client: TestClient) -> None:
    respuesta = client.get(f"/v1/votaciones/{V1}/bancadas")
    assert respuesta.status_code == 200
    tabla = respuesta.json()
    assert tabla["columnas"] == ["Bancada", "A favor", "En contra", "Abstención", "Total"]
    assert tabla["filas"][0] == ["Fuerza Popular", 2, 0, 0, 2]


def test_listar_votos_por_posicion(client: TestClient) -> None:
    respuesta = client.get(f"/v1/votaciones/{V1}/votos", params={"posicion": "en_contra"})
    assert respuesta.status_code == 200
    assert [fila[0] for fila in respuesta.json()["filas"]] == ["Eva Rojas"]

    invalida = client.get(f"/v1/votaciones/{V1}/votos", params={"posicion": "otra"})
    assert invalida.status_code == 422


def test_no_voto_se_deriva_por_complemento(client: TestClient) -> None:
    respuesta = client.get(f"/v1/votaciones/{V1}/votos", params={"posicion": "no_voto"})
    assert respuesta.status_code == 200
    assert respuesta.json()["metadata"]["derivado"] is True


def test_congresistas_y_historial(client: TestClient) -> None:
    padron = client.get("/v1/congresistas", params={"buscar": "ana"})
    assert padron.status_code == 200
    assert [item["nombre"] for item in padron.json()] == ["Ana Torres"]

    historial = client.get("/v1/congresistas/Ana Torres/historial")
    assert historial.status_code == 200
    tabla = historial.json()
    assert len(tabla["filas"]) == 2
    assert all(fila[0] == "Ana Torres" for fila in tabla["filas"])


def test_catalogo_de_legislaturas_tipos_y_bancadas(client: TestClient) -> None:
    legislaturas = client.get("/v1/legislaturas")
    assert legislaturas.status_code == 200
    assert {fila["id"] for fila in legislaturas.json()} == {
        "2025-2026-L1",
        "2025-2026-L2",
    }

    tipos = client.get("/v1/tipos")
    assert tipos.json() == ["moción", "proyecto"]

    bancadas = client.get("/v1/bancadas")
    assert {fila["bancada"] for fila in bancadas.json()} == {
        "Fuerza Popular",
        "Perú Libre",
    }


def test_listar_actas(client: TestClient) -> None:
    respuesta = client.get("/v1/actas")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 2
    assert cuerpo["items"][0]["acta_id"] == "2026-03-05-01"
    assert cuerpo["items"][0]["votaciones"] == 1


def test_consulta_determinista_sin_llm(client: TestClient) -> None:
    respuesta = client.post(
        "/v1/consulta",
        json={"pregunta": "¿Cómo votó cada bancada en la moción 1486?", "usar_llm": False},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["confianza"] == "alta"
    assert cuerpo["tabla"]["columnas"][0] == "Bancada"
    assert cuerpo["fuentes"][0]["acta_id"] == "2026-03-05-01"
    assert cuerpo["fuentes"][0]["pdf_url"] == "https://example.com/acta.pdf"


def test_consulta_valida_pregunta_corta(client: TestClient) -> None:
    respuesta = client.post("/v1/consulta", json={"pregunta": "¿?", "usar_llm": False})
    assert respuesta.status_code == 422


def test_exportacion_excel_y_word(client: TestClient) -> None:
    payload = {"pregunta": "¿Cómo votó cada bancada en la moción 1486?", "usar_llm": False}

    excel = client.post("/v1/consulta/export", json=payload, params={"formato": "excel"})
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    )
    assert excel.content[:2] == b"PK"
    assert "congress_rag_consulta.xlsx" in excel.headers["content-disposition"]

    word = client.post("/v1/consulta/export", json=payload, params={"formato": "word"})
    assert word.status_code == 200
    assert word.content[:2] == b"PK"
    assert "congress_rag_consulta.docx" in word.headers["content-disposition"]


def test_calidad_resumen(client: TestClient) -> None:
    respuesta = client.get("/v1/calidad/resumen")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["votaciones"] == 2
    assert cuerpo["votos"] == 8
    assert cuerpo["confianza_votos"]["alta"] == 2


def test_api_sin_base_responde_503(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "db_path", tmp_path / "inexistente.db")
    app = create_app()
    with TestClient(app) as cliente:
        respuesta = cliente.get("/v1/votaciones")
    assert respuesta.status_code == 503
    assert "ingest.py" in respuesta.json()["detail"]
