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
    plan = route("¿Cómo votó cada bancada en la moción 19785?", _ProveedorFalso(propuesto))
    assert plan.filtros.proyecto_o_mocion == "moción 19785"
    assert plan.filtros.tipo == "moción"


def test_no_se_descarta_una_consulta_con_entidades_por_fuera_de_alcance() -> None:
    propuesto = QueryPlan(intencion="fuera_de_alcance")
    plan = route("¿Cómo votó cada bancada en la moción 19785?", _ProveedorFalso(propuesto))
    assert plan.intencion == "agregacion"
    assert plan.filtros.proyecto_o_mocion == "moción 19785"


def test_se_conserva_la_intencion_del_llm_sin_entidades() -> None:
    propuesto = QueryPlan(
        intencion="busqueda",
        requiere_sql=False,
        requiere_contexto=True,
        consulta_reescrita="resumen del debate",
    )
    plan = route("¿Qué se debatió sobre la situación del país?", _ProveedorFalso(propuesto))
    assert plan.intencion == "busqueda"
    assert plan.consulta_reescrita == "resumen del debate"
    assert plan.filtros == Filtros()


def test_detecta_acta_y_prioriza_sql() -> None:
    plan = route("¿Qué se votó en el acta 2025-10-10-20?")
    assert plan.filtros.acta_id == "2025-10-10-20"
    assert plan.intencion == "agregacion"
    assert plan.requiere_sql is True


def test_una_pregunta_sin_entidad_va_a_recuperacion_textual() -> None:
    plan = route("reforma del transporte público")
    assert plan.intencion == "busqueda"
    assert plan.requiere_contexto is True
    assert plan.requiere_sql is False


def test_debate_sobre_una_mocion_usa_sql_y_texto() -> None:
    plan = route("¿Qué se debatió sobre la moción 19785?")
    assert plan.intencion == "mixta"
    assert plan.requiere_sql is True
    assert plan.requiere_contexto is True
    assert plan.filtros.proyecto_o_mocion == "moción 19785"


def test_el_llm_no_puede_borrar_el_acta_detectada_por_reglas() -> None:
    propuesto = QueryPlan(
        intencion="busqueda",
        filtros=Filtros(),
        requiere_sql=False,
        requiere_contexto=True,
    )
    plan = route("¿Qué se discutió en el acta 2025-10-10-20?", _ProveedorFalso(propuesto))
    assert plan.filtros.acta_id == "2025-10-10-20"
