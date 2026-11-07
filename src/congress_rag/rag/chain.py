"""Cadena RAG: router -> SQL / recuperación -> LLM -> respuesta con citas."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from congress_rag.ingestion.normalize import normalize_key
from congress_rag.rag import sql_tools
from congress_rag.rag.llm import LLMProvider
from congress_rag.rag.prompts import build_user_prompt
from congress_rag.rag.retriever import Retriever
from congress_rag.rag.router import route
from congress_rag.schemas import Answer, Filtros, Fuente, QueryPlan, TableSpec

SIN_EVIDENCIA = "No se encontró evidencia en el corpus para responder esta consulta."


def _buscar_votacion(
    session: Session, plan: QueryPlan, pregunta: str, retriever: Retriever | None
) -> dict[str, Any] | None:
    filtros = plan.filtros

    if filtros.proyecto_o_mocion:
        filas = sql_tools.listar_votaciones(
            session,
            filtros=Filtros(legislatura=filtros.legislatura, tipo=filtros.tipo),
            texto=filtros.proyecto_o_mocion,
            limit=10,
        )
        if filas:
            return filas[0]

    if filtros.acta_id:
        filas = sql_tools.listar_votaciones(
            session, filtros=Filtros(acta_id=filtros.acta_id), limit=10
        )
        if filas:
            return filas[0]

    # Respaldo: coincidencia de términos del título (p. ej. "cuestión de confianza").
    filas = sql_tools.buscar_votaciones_por_texto(
        session,
        plan.consulta_reescrita or pregunta,
        filtros=Filtros(legislatura=filtros.legislatura),
    )
    if filas:
        return filas[0]

    if retriever is not None:
        try:
            resultados = retriever.search(pregunta, top_k=3)
            for resultado in resultados:
                votacion_id = resultado["metadata"].get("votacion_id")
                if votacion_id:
                    contexto = sql_tools.obtener_votacion(session, votacion_id)
                    if contexto:
                        return contexto
        except Exception:
            pass

    return None


def _fuentes_votacion(contexto: dict[str, Any]) -> Fuente:
    return Fuente(
        acta_id=contexto["acta_id"],
        pagina=contexto.get("pagina_inicio"),
        pdf_url=contexto.get("pdf_url"),
        votacion_id=contexto.get("votacion_id"),
    )


def _contexto_narrativo(
    pregunta: str, retriever: Retriever | None, top_k: int = 4
) -> tuple[str, list[Fuente]]:
    if retriever is None:
        return "", []
    try:
        resultados = retriever.search(pregunta, top_k=top_k)
    except Exception:
        return "", []

    fragmentos: list[str] = []
    fuentes: list[Fuente] = []
    for resultado in resultados:
        metadata = resultado["metadata"]
        fragmentos.append(
            f"[Acta {metadata.get('acta_id')}, pág. {metadata.get('pagina')}]\n"
            f"{resultado['texto'][:1500]}"
        )
        fuentes.append(
            Fuente(
                acta_id=str(metadata.get("acta_id") or ""),
                pagina=metadata.get("pagina"),
                votacion_id=metadata.get("votacion_id") or None,
            )
        )
    return "\n\n".join(fragmentos), fuentes


def _tabla_para_consulta(
    session: Session,
    contexto: dict[str, Any],
    plan: QueryPlan,
    pregunta: str,
) -> TableSpec:
    """Elige la tabla adecuada según la intención detectada en la pregunta."""

    votacion_id = contexto["votacion_id"]
    clave = normalize_key(pregunta).lower()

    if plan.filtros.bancada:
        return sql_tools.comparar_bancadas(
            session, votacion_id, plan.filtros.bancada, plan.filtros.bancada
        )

    if "congresistas" in clave or "quienes" in clave or "listado" in clave:
        if "encontra" in clave:
            return sql_tools.lista_votos(session, votacion_id, -1)
        if "abstencion" in clave or "abstuvieron" in clave:
            return sql_tools.lista_votos(session, votacion_id, 0)
        if "favor" in clave:
            return sql_tools.lista_votos(session, votacion_id, 1)

    return sql_tools.conteo_por_bancada(session, votacion_id)


def _resumen_determinista(
    contexto: dict[str, Any] | None, tabla: TableSpec | None
) -> str:
    if not contexto or not tabla or not tabla.filas:
        return SIN_EVIDENCIA

    lineas = [
        f"Votación: {contexto['titulo']}",
        (
            f"Acta {contexto['acta_id']} · Página {contexto.get('pagina_inicio')} · "
            f"Legislatura {contexto.get('legislatura_id')}"
        ),
        (
            f"Resultado: {contexto.get('conteo_si', 0)} a favor, "
            f"{contexto.get('conteo_no', 0)} en contra, "
            f"{contexto.get('conteo_abstencion', 0)} abstenciones."
        ),
        "",
    ]

    if tabla.columnas[:1] == ["Bancada"]:
        lineas.append("Distribución por bancada:")
        for fila in tabla.filas:
            lineas.append(
                f"- {fila[0]}: {fila[1]} a favor, {fila[2]} en contra, "
                f"{fila[3]} abstenciones."
            )
    elif tabla.columnas[:1] == ["Congresista"]:
        lineas.append(f"{tabla.titulo}:")
        for fila in tabla.filas:
            lineas.append(f"- {fila[0]} ({fila[1]})")
    else:
        lineas.append(f"{tabla.titulo}:")
        for fila in tabla.filas:
            lineas.append("- " + " · ".join(str(valor) for valor in fila))

    return "\n".join(lineas)


def _deduplicar_fuentes(fuentes: list[Fuente]) -> list[Fuente]:
    vistas: set[tuple[str, int | None, str | None]] = set()
    resultado: list[Fuente] = []
    for fuente in fuentes:
        clave = (fuente.acta_id, fuente.pagina, fuente.votacion_id)
        if clave in vistas:
            continue
        vistas.add(clave)
        resultado.append(fuente)
    return resultado


def answer_question(
    session: Session,
    pregunta: str,
    *,
    provider: LLMProvider | None = None,
    retriever: Retriever | None = None,
    use_llm: bool = True,
) -> Answer:
    plan = route(pregunta, provider if use_llm else None)

    if plan.intencion == "fuera_de_alcance":
        return Answer(
            pregunta=pregunta,
            respuesta=SIN_EVIDENCIA,
            confianza="baja",
            advertencias=["La consulta está fuera del alcance del corpus cargado."],
        )

    contexto = _buscar_votacion(session, plan, pregunta, retriever)
    tabla: TableSpec | None = None
    fuentes: list[Fuente] = []

    if contexto and plan.requiere_sql:
        tabla = _tabla_para_consulta(session, contexto, plan, pregunta)
        fuentes.append(_fuentes_votacion(contexto))
    elif contexto:
        fuentes.append(_fuentes_votacion(contexto))

    narrativa = ""
    if plan.requiere_contexto:
        narrativa, fuentes_narrativa = _contexto_narrativo(pregunta, retriever)
        fuentes.extend(fuentes_narrativa)

    fuentes = _deduplicar_fuentes(fuentes)

    advertencias: list[str] = []
    if plan.requiere_contexto and not narrativa:
        advertencias.append(
            "No se recuperó contexto narrativo; la respuesta se limita a la capa "
            "estructurada. Construye el índice vectorial para preguntas de debate."
        )
    if not tabla and not narrativa:
        advertencias.append("No se recuperó una votación ni contexto verificable.")

    if provider is not None and use_llm:
        prompt = build_user_prompt(
            pregunta,
            tabla=tabla,
            contexto=narrativa,
            fuentes=[
                f"Acta {fuente.acta_id}, pág. {fuente.pagina}"
                for fuente in fuentes
                if fuente.acta_id
            ],
        )
        try:
            respuesta = str(provider.generate(prompt))
        except Exception as exc:
            respuesta = _resumen_determinista(contexto, tabla)
            return Answer(
                pregunta=pregunta,
                respuesta=respuesta,
                fuentes=fuentes,
                tabla=tabla,
                confianza="media" if tabla else "baja",
                advertencias=[f"LLM no disponible: {exc}", *advertencias],
            )
    else:
        respuesta = _resumen_determinista(contexto, tabla)

    if plan.requiere_contexto and not narrativa:
        confianza = "media" if tabla and tabla.filas else "baja"
    elif tabla and tabla.filas:
        confianza = "alta"
    else:
        confianza = "media" if fuentes else "baja"

    return Answer(
        pregunta=pregunta,
        respuesta=respuesta,
        fuentes=fuentes,
        tabla=tabla,
        confianza=confianza,
        advertencias=advertencias,
    )
