"""Pruebas de la cadena RAG: recuperación sin LLM y redacción validada."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from congress_rag.db.models import Base
from congress_rag.rag.chain import (
    _fragmentos_texto,
    _tabla_conteo_corpus,
    answer_question,
)
from congress_rag.schemas import QueryPlan

PREGUNTA_DEBATE = "¿Qué se debatió sobre la reforma del transporte?"


class _RetrieverFalso:
    """Devuelve pasajes fijos y registra los filtros recibidos."""

    def __init__(self, resultados: list[dict[str, Any]]) -> None:
        self.resultados = resultados
        self.llamadas: list[dict[str, Any]] = []

    def search(
        self,
        pregunta: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        self.llamadas.append({"where": where, "min_score": min_score})
        return list(self.resultados)


class _ProveedorFalso:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.llamado = False

    def name(self) -> str:
        return "falso"

    def generate(self, prompt: str, schema: object = None) -> str:
        self.llamado = True
        return self.texto


class _ProveedorProhibido:
    def name(self) -> str:
        return "prohibido"

    def generate(self, prompt: str, schema: object = None) -> str:
        raise AssertionError("No debe llamarse al LLM")


def _resultado(pagina: int = 97, score: float = 0.84) -> dict[str, Any]:
    return {
        "id": f"narrativa:2026-06-03-10:{pagina}",
        "texto": "La congresista expuso los alcances de la reforma del transporte.",
        "metadata": {
            "acta_id": "2026-06-03-10",
            "pagina": pagina,
            "tipo": "narrativa",
            "votacion_id": "",
        },
        "score": score,
        "distancia": 1 - score,
    }


def _sesion(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", future=True)
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_consulta_de_debate_sin_llm_devuelve_extracto_con_cita(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    with _sesion(tmp_path) as session:
        answer = answer_question(
            session,
            PREGUNTA_DEBATE,
            provider=_ProveedorProhibido(),
            retriever_narrativa=retriever,
            use_llm=False,
        )

    assert answer.modo == "extractivo"
    assert "Acta 2026-06-03-10" in answer.respuesta
    assert "pág. 97" in answer.respuesta
    assert answer.fragmentos[0].acta_id == "2026-06-03-10"
    assert answer.tabla is None
    assert retriever.llamadas[0]["min_score"] is not None


def test_el_llm_no_se_invoca_si_se_desactiva(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    with _sesion(tmp_path) as session:
        answer = answer_question(
            session,
            PREGUNTA_DEBATE,
            provider=_ProveedorProhibido(),
            retriever_narrativa=retriever,
            use_llm=False,
        )

    assert answer.modo == "extractivo"


def test_se_descarta_una_cifra_inventada_por_el_llm(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    proveedor = _ProveedorFalso("La reforma obtuvo 9999 votos [Acta 2026-06-03-10, pág. 97].")
    with _sesion(tmp_path) as session:
        answer = answer_question(
            session,
            PREGUNTA_DEBATE,
            provider=proveedor,
            retriever_narrativa=retriever,
            use_llm=True,
        )

    assert proveedor.llamado
    assert answer.modo == "extractivo"
    assert "9999" not in answer.respuesta
    assert any("Se descartó la redacción" in aviso for aviso in answer.advertencias)


def test_se_descarta_una_redaccion_que_omite_la_cita(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    proveedor = _ProveedorFalso("El debate trató sobre la reforma del transporte.")
    with _sesion(tmp_path) as session:
        answer = answer_question(
            session,
            PREGUNTA_DEBATE,
            provider=proveedor,
            retriever_narrativa=retriever,
            use_llm=True,
        )

    assert answer.modo == "extractivo"
    assert "Acta 2026-06-03-10" in answer.respuesta


def test_una_redaccion_valida_conserva_citas_y_cifras(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    proveedor = _ProveedorFalso(
        "El debate trató sobre la reforma del transporte [Acta 2026-06-03-10, pág. 97]."
    )
    with _sesion(tmp_path) as session:
        answer = answer_question(
            session,
            PREGUNTA_DEBATE,
            provider=proveedor,
            retriever_narrativa=retriever,
            use_llm=True,
        )

    assert answer.modo == "redactado"
    assert answer.respuesta == proveedor.texto


def test_filtra_por_acta_cuando_la_pregunta_la_nombra(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    with _sesion(tmp_path) as session:
        answer_question(
            session,
            "¿Qué se debatió en el acta 2026-06-03-10?",
            retriever_narrativa=retriever,
            use_llm=False,
        )

    assert retriever.llamadas[0]["where"] == {"acta_id": "2026-06-03-10"}


def test_un_conteo_de_una_votacion_no_es_conteo_del_corpus(tmp_path) -> None:
    with _sesion(tmp_path) as session:
        assert (
            _tabla_conteo_corpus(session, "¿Cuántos votos hubo en la cuestión de confianza?")
            is None
        )
        assert _tabla_conteo_corpus(session, "¿Cuántas actas hay?") is not None


def test_el_contexto_de_una_votacion_acota_el_texto_a_su_acta(tmp_path) -> None:
    retriever = _RetrieverFalso([_resultado()])
    with _sesion(tmp_path) as session:
        _fragmentos_texto(
            session,
            "debate de la moción",
            retriever,
            QueryPlan(intencion="mixta"),
            acta_id="2026-06-03-10",
        )

    assert retriever.llamadas[0]["where"] == {"acta_id": "2026-06-03-10"}
