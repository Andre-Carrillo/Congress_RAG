"""Cadena RAG: recuperación determinista (SQL + texto) y redacción opcional.

La recuperación funciona sin LLM. El modelo, cuando está disponible, solo
reformula la RESPUESTA BASE ya construida a partir de la tabla y los fragmentos
literales de las actas; nunca decide qué se recupera ni calcula cifras.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from congress_rag.config import settings
from congress_rag.db.models import (
    Congresista,
    Documento,
    Legislatura,
    Votacion,
    Voto,
)
from congress_rag.ingestion.normalize import normalize_key, strip_accents
from congress_rag.rag import sql_tools
from congress_rag.rag.llm import LLMProvider
from congress_rag.rag.prompts import build_adapter_prompt
from congress_rag.rag.retriever import Retriever
from congress_rag.rag.router import route
from congress_rag.schemas import Answer, Filtros, Fragmento, Fuente, QueryPlan, TableSpec

SIN_EVIDENCIA = "No se encontró evidencia en el corpus para responder esta consulta."

# Acepta "[Acta 2025-10-10-20, pág. 7]" y "Acta 2025-10-10-20 · Página 7".
CITA_RE = re.compile(
    r"acta\s+(\d{4}-\d{2}-\d{2}-\d{2})\D{0,12}?p[áa]g(?:ina)?\.?\s*(\d+)",
    re.IGNORECASE,
)
NUMERO_RE = re.compile(r"\d+")

LARGO_EXTRACTO = 700

MODELOS_CONTEO = [
    ("actas", r"\bactas?\b|\bdocumentos?\b", Documento),
    ("votaciones", r"\bvotaciones?\b", Votacion),
    ("votos", r"\bvotos?\b", Voto),
    ("congresistas", r"\bcongresistas?\b|\bparlamentarios?\b", Congresista),
    ("legislaturas", r"\blegislaturas?\b", Legislatura),
]


# ---------------------------------------------------------------------------
# Recuperación estructurada (SQL)
# ---------------------------------------------------------------------------
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
            resultados = retriever.search(pregunta, top_k=3, min_score=settings.min_score)
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


def _tabla_conteo_corpus(session: Session, pregunta: str) -> TableSpec | None:
    """Responde conteos del corpus ("¿cuántas actas hay?") sin LLM ni vectores."""

    texto = strip_accents(pregunta).lower()
    if not re.search(r"\bcuant|\bnumero de\b|\btotal de\b|\bconteo\b", texto):
        return None

    # Una pregunta sobre un hecho concreto ("¿cuántos votos en la cuestión de
    # confianza?") no es un conteo del corpus: debe resolverla la votación.
    if re.search(
        r"\bmocion|\bproyecto|\bcuestion|\bconfianza|\binterpelacion|\bcensura",
        texto,
    ):
        return None

    filas: list[list[Any]] = []
    for etiqueta, patron, modelo in MODELOS_CONTEO:
        if not re.search(patron, texto):
            continue
        total = int(session.scalar(select(func.count()).select_from(modelo)) or 0)
        filas.append([etiqueta.capitalize(), total])

    if not filas:
        return None
    return TableSpec(
        titulo="Conteo del corpus",
        columnas=["Métrica", "Total"],
        filas=filas,
        metadata={"fuente": "sql"},
    )


# ---------------------------------------------------------------------------
# Recuperación textual (ChromaDB)
# ---------------------------------------------------------------------------
def _mapa_pdf(session: Session, acta_ids: set[str]) -> dict[str, str | None]:
    """Devuelve el enlace al PDF de cada acta recuperada."""

    limpios = sorted(acta for acta in acta_ids if acta)
    if not limpios:
        return {}
    filas = session.execute(
        select(Documento.acta_id, Documento.pdf_url).where(Documento.acta_id.in_(limpios))
    ).all()
    return {acta_id: url for acta_id, url in filas}


def _filtro_texto(plan: QueryPlan) -> dict[str, Any] | None:
    """Acota la búsqueda textual cuando la pregunta nombra un acta o legislatura."""

    filtros = plan.filtros
    if filtros.acta_id:
        return {"acta_id": filtros.acta_id}
    if filtros.legislatura:
        return {"legislatura_id": filtros.legislatura}
    return None


def _fragmentos_texto(
    session: Session,
    pregunta: str,
    retriever: Retriever | None,
    plan: QueryPlan,
    acta_id: str | None = None,
) -> list[Fragmento]:
    """Recupera pasajes literales de las actas. Funciona sin LLM.

    Si hay una votación identificada, ``acta_id`` acota el texto a esa acta para
    que los pasajes acompañen a la tabla en vez de venir de sesiones ajenas.
    """

    if retriever is None:
        return []
    where = {"acta_id": acta_id} if acta_id else _filtro_texto(plan)
    try:
        resultados = retriever.search(
            pregunta,
            top_k=settings.top_k_narrativa,
            where=where,
            min_score=settings.min_score_narrativa,
        )
    except Exception:
        return []

    if not resultados:
        return []

    mejor = float(resultados[0]["score"])
    umbral = max(settings.min_score_narrativa, mejor - settings.margen_score_narrativa)
    seleccion = [item for item in resultados if float(item["score"]) >= umbral]
    pdfs = _mapa_pdf(session, {str(item["metadata"].get("acta_id") or "") for item in seleccion})

    fragmentos: list[Fragmento] = []
    for item in seleccion:
        metadata = item["metadata"]
        acta_id = str(metadata.get("acta_id") or "")
        fragmentos.append(
            Fragmento(
                acta_id=acta_id,
                pagina=metadata.get("pagina"),
                score=round(float(item["score"]), 4),
                texto=str(item["texto"]),
                votacion_id=metadata.get("votacion_id") or None,
                pdf_url=pdfs.get(acta_id),
            )
        )
    return fragmentos


def _fuentes_de_fragmentos(fragmentos: list[Fragmento]) -> list[Fuente]:
    return [
        Fuente(
            acta_id=fragmento.acta_id,
            pagina=fragmento.pagina,
            pdf_url=fragmento.pdf_url,
            votacion_id=fragmento.votacion_id,
        )
        for fragmento in fragmentos
        if fragmento.acta_id
    ]


# ---------------------------------------------------------------------------
# Respuestas deterministas (sin LLM)
# ---------------------------------------------------------------------------
def _recortar(texto: str, limite: int = LARGO_EXTRACTO) -> str:
    limpio = " ".join(texto.split())
    if len(limpio) <= limite:
        return limpio
    return limpio[:limite].rsplit(" ", 1)[0] + "…"


def _resumen_determinista(contexto: dict[str, Any] | None, tabla: TableSpec | None) -> str:
    if not contexto or not tabla or not tabla.filas:
        return SIN_EVIDENCIA

    lineas = [
        f"Votación: {contexto['titulo']}",
        (
            f"[Acta {contexto['acta_id']}, pág. {contexto.get('pagina_inicio')}] · "
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
                f"- {fila[0]}: {fila[1]} a favor, {fila[2]} en contra, {fila[3]} abstenciones."
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


def _resumen_tabla(tabla: TableSpec) -> str:
    lineas = [f"{tabla.titulo}:"]
    for fila in tabla.filas:
        lineas.append("- " + " · ".join(str(valor) for valor in fila))
    return "\n".join(lineas)


def _resumen_extractivo(fragmentos: list[Fragmento]) -> str:
    if not fragmentos:
        return SIN_EVIDENCIA

    lineas = [f"Fragmentos recuperados del texto de las actas ({len(fragmentos)}):"]
    for fragmento in fragmentos:
        pagina = f"pág. {fragmento.pagina}" if fragmento.pagina else "página s/d"
        lineas.extend(
            [
                "",
                (f"[Acta {fragmento.acta_id}, {pagina} · score {fragmento.score:.3f}]"),
                _recortar(fragmento.texto),
            ]
        )
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


# ---------------------------------------------------------------------------
# Validación de la redacción del LLM
# ---------------------------------------------------------------------------
def _validar_redaccion(
    texto: str,
    numeros_permitidos: set[str],
    firmas: set[tuple[str, int]],
    firmas_base: set[tuple[str, int]],
) -> bool:
    """Rechaza redacciones que inventen citas, omitan fuentes o alteren cifras."""

    if not texto.strip():
        return False

    citas = {(acta_id, int(pagina)) for acta_id, pagina in CITA_RE.findall(texto)}
    if citas - firmas:
        return False
    if firmas_base and not firmas_base <= citas:
        return False

    return not (set(NUMERO_RE.findall(texto)) - numeros_permitidos)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def answer_question(
    session: Session,
    pregunta: str,
    *,
    provider: LLMProvider | None = None,
    retriever_votaciones: Retriever | None = None,
    retriever_narrativa: Retriever | None = None,
    use_llm: bool = True,
    retriever: Retriever | None = None,
) -> Answer:
    """Responde con recuperación determinista y redacción opcional.

    ``retriever`` se mantiene por compatibilidad y se interpreta como el
    retriever de votaciones.
    """

    if retriever is not None and retriever_votaciones is None:
        retriever_votaciones = retriever

    # La selección de fuentes y de rutas es determinista. El proveedor solo se
    # usa después, como adaptador de la respuesta base ya recuperada.
    plan = route(pregunta)

    if plan.intencion == "fuera_de_alcance":
        return Answer(
            pregunta=pregunta,
            respuesta=SIN_EVIDENCIA,
            confianza="baja",
            advertencias=["La consulta está fuera del alcance del corpus cargado."],
        )

    # 1) Recuperación estructurada. Los conteos del corpus no dependen de una
    # votación concreta y se resuelven antes de buscar por texto.
    tabla: TableSpec | None = None
    filtros = plan.filtros
    if plan.requiere_sql and not any(
        (filtros.proyecto_o_mocion, filtros.acta_id, filtros.bancada, filtros.congresista)
    ):
        tabla = _tabla_conteo_corpus(session, pregunta)

    contexto = (
        _buscar_votacion(session, plan, pregunta, retriever_votaciones)
        if plan.requiere_sql and tabla is None
        else None
    )
    fuentes: list[Fuente] = []
    if contexto:
        fuentes.append(_fuentes_votacion(contexto))
        if plan.requiere_sql and tabla is None:
            tabla = _tabla_para_consulta(session, contexto, plan, pregunta)

    # 2) Recuperación textual sobre las actas.
    fragmentos = (
        _fragmentos_texto(
            session,
            pregunta,
            retriever_narrativa,
            plan,
            acta_id=contexto.get("acta_id") if contexto else None,
        )
        if plan.requiere_contexto
        else []
    )
    fuentes.extend(_fuentes_de_fragmentos(fragmentos))
    fuentes = _deduplicar_fuentes(fuentes)

    # 3) Respuesta base, construida sin LLM. En consultas mixtas se muestran
    # tanto la tabla como los pasajes: una capa no tapa a la otra.
    bloques: list[str] = []
    if tabla and tabla.filas:
        bloques.append(
            _resumen_determinista(contexto, tabla) if contexto else _resumen_tabla(tabla)
        )
    if fragmentos:
        bloques.append(_resumen_extractivo(fragmentos))
    base = "\n\n".join(bloques) if bloques else SIN_EVIDENCIA

    advertencias: list[str] = []
    if plan.requiere_contexto and not fragmentos:
        advertencias.append(
            "No se recuperó texto de las actas para esta consulta; la respuesta se "
            "limita a la capa estructurada. Revisa el índice vectorial de 'narrativa'."
        )
    if not tabla and not fragmentos:
        advertencias.append("No se recuperó una votación ni contexto verificable.")

    # 4) Redacción opcional: el LLM solo reformula la respuesta base.
    respuesta = base
    modo = "extractivo"

    if provider is not None and use_llm and ((tabla and tabla.filas) or fragmentos):
        prompt = build_adapter_prompt(
            pregunta,
            base,
            tabla=tabla,
            fragmentos=[
                f"[Acta {fragmento.acta_id}, pág. {fragmento.pagina}] {fragmento.texto[:800]}"
                for fragmento in fragmentos
            ],
            fuentes=[
                f"Acta {fuente.acta_id}, pág. {fuente.pagina}"
                for fuente in fuentes
                if fuente.acta_id
            ],
        )
        try:
            propuesta = str(provider.generate(prompt)).strip()
        except Exception as exc:
            advertencias.insert(0, f"LLM no disponible: {exc}")
        else:
            # La pregunta y las instrucciones no son evidencia. Solo se
            # permiten números que ya estén en la respuesta base verificada.
            permitidos = set(NUMERO_RE.findall(base))
            firmas = {
                (fuente.acta_id, int(fuente.pagina))
                for fuente in fuentes
                if fuente.acta_id and fuente.pagina is not None
            }
            firmas_base = {(acta_id, int(pagina)) for acta_id, pagina in CITA_RE.findall(base)}
            if _validar_redaccion(propuesta, permitidos, firmas, firmas_base):
                respuesta, modo = propuesta, "redactado"
            else:
                advertencias.append(
                    "Se descartó la redacción del LLM porque inventó citas o cifras, "
                    "o porque omitió fuentes de la respuesta base."
                )

    # 5) Confianza según la evidencia realmente recuperada.
    if tabla and tabla.filas:
        confianza = "media" if (plan.requiere_contexto and not fragmentos) else "alta"
    elif fragmentos:
        confianza = "alta" if fragmentos[0].score >= 0.88 else "media"
    elif contexto:
        confianza = "media"
    else:
        confianza = "baja"

    return Answer(
        pregunta=pregunta,
        respuesta=respuesta,
        fuentes=fuentes,
        tabla=tabla,
        fragmentos=fragmentos,
        confianza=confianza,
        modo=modo,
        advertencias=advertencias,
    )
