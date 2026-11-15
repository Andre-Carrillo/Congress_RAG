"""Pruebas del router híbrido (reglas + LLM)."""

from __future__ import annotations

from congress_rag.rag.router import route
from congress_rag.schemas import Filtros, QueryPlan


class _ProveedorFalso:
    def __init__(self, plan: QueryPlan) -> None:
        self.plan = plan

    def name(self) -> str:
        return "falso"

    def generate(self, prompt: str, schema: object = None) -> QueryPlan:
        return self.plan


def test_prevalece_la_mocion_detectada_por_reglas() -> None:
    propuesto = QueryPlan(
        intencion="agregacion",
        filtros=Filtros(proyecto_o_mocion="19785"),
        requiere_sql=True,
    )
    plan = route(
        "¿Cómo votó cada bancada en la moción 19785?", _ProveedorFalso(propuesto)
    )
    assert plan.filtros.proyecto_o_mocion == "moción 19785"
    assert plan.filtros.tipo == "moción"


def test_no_se_descarta_una_consulta_con_entidades_por_fuera_de_alcance() -> None:
    propuesto = QueryPlan(intencion="fuera_de_alcance")
    plan = route(
        "¿Cómo votó cada bancada en la moción 19785?", _ProveedorFalso(propuesto)
    )
    assert plan.intencion == "agregacion"
    assert plan.filtros.proyecto_o_mocion == "moción 19785"


def test_se_conserva_la_intencion_del_llm_sin_entidades() -> None:
    propuesto = QueryPlan(
        intencion="busqueda",
        requiere_sql=False,
        requiere_contexto=True,
        consulta_reescrita="resumen del debate",
    )
    plan = route(
        "¿Qué se debatió sobre la situación del país?", _ProveedorFalso(propuesto)
    )
    assert plan.intencion == "busqueda"
    assert plan.consulta_reescrita == "resumen del debate"
    assert plan.filtros == Filtros()
