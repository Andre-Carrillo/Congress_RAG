"""Consultas SQL deterministas. El LLM nunca genera SQL libre."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from congress_rag.db.models import Congresista, Documento, Votacion, Voto
from congress_rag.ingestion.normalize import normalize_key, strip_accents
from congress_rag.schemas import Filtros, Posicion, TableSpec

LABEL = {1: "A favor", -1: "En contra", 0: "Abstención", 2: "No votó"}

STOPWORDS = {
    "como",
    "cada",
    "cual",
    "cuales",
    "cuanto",
    "cuanta",
    "cuantos",
    "cuantas",
    "donde",
    "cuando",
    "sobre",
    "entre",
    "antes",
    "despues",
    "para",
    "porque",
    "sesion",
    "votacion",
    "votaciones",
    "votaron",
    "votos",
    "resultado",
    "congresista",
    "congresistas",
    "bancada",
    "bancadas",
    "legislatura",
    "lista",
    "listado",
    "ordenada",
    "abstenciones",
    "favor",
    "contra",
    "tuvo",
    "hubo",
    "fue",
    "esta",
    "este",
    "unos",
    "unas",
    "del",
    "las",
    "los",
    "que",
}


def _pk(session: Session, votacion_id: str) -> int | None:
    return session.scalar(select(Votacion.id).where(Votacion.votacion_id == votacion_id))


def listar_votaciones(
    session: Session,
    filtros: Filtros | None = None,
    texto: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filtros = filtros or Filtros()
    stmt = (
        select(
            Votacion.votacion_id,
            Votacion.titulo,
            Votacion.tipo,
            Votacion.pagina_inicio,
            Votacion.conteo_si,
            Votacion.conteo_no,
            Votacion.conteo_abstencion,
            Documento.acta_id,
            Documento.fecha,
            Documento.legislatura_id,
            Documento.pdf_url,
        )
        .join(Documento, Votacion.documento_id == Documento.id)
        .order_by(Documento.fecha.desc(), Votacion.indice_votacion)
    )
    if filtros.legislatura:
        stmt = stmt.where(Documento.legislatura_id == filtros.legislatura)
    if filtros.acta_id:
        stmt = stmt.where(Documento.acta_id == filtros.acta_id)
    if filtros.tipo:
        stmt = stmt.where(Votacion.tipo == filtros.tipo)
    if texto:
        clave = normalize_key(texto)
        if clave:
            stmt = stmt.where(Votacion.titulo_normalizado.contains(clave))

    return [dict(fila._mapping) for fila in session.execute(stmt.limit(limit)).all()]


def _tokens(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", strip_accents(texto).lower())


def buscar_votaciones_por_texto(
    session: Session,
    consulta: str,
    filtros: Filtros | None = None,
    limit: int = 10,
    minimo_terminos: int = 1,
) -> list[dict[str, Any]]:
    """Busca votaciones por coincidencia de términos del título.

    Se usa como respaldo cuando la pregunta no incluye un número de moción,
    proyecto o acta. Devuelve primero las votaciones con más términos en común
    y, a igual puntaje, las más recientes. La comparación es por palabra
    completa para evitar que ``2050`` coincida con ``12050``.
    """

    filas = listar_votaciones(session, filtros=filtros, limit=2000)
    terminos = [
        termino
        for termino in _tokens(consulta)
        if len(termino) >= 4 and termino not in STOPWORDS
    ]
    if not terminos or not filas:
        return []

    puntuadas: list[tuple[int, dict[str, Any]]] = []
    for fila in filas:
        palabras = set(_tokens(fila["titulo"]))
        puntaje = sum(1 for termino in terminos if termino in palabras)
        if puntaje >= minimo_terminos:
            puntuadas.append((puntaje, fila))

    puntuadas.sort(key=lambda item: item[1]["fecha"] or "", reverse=True)
    puntuadas.sort(key=lambda item: item[0], reverse=True)
    return [fila for _, fila in puntuadas[:limit]]


def obtener_votacion(session: Session, votacion_id: str) -> dict[str, Any] | None:
    fila = session.execute(
        select(
            Votacion.votacion_id,
            Votacion.titulo,
            Votacion.tipo,
            Votacion.pagina_inicio,
            Votacion.conteo_si,
            Votacion.conteo_no,
            Votacion.conteo_abstencion,
            Documento.acta_id,
            Documento.fecha,
            Documento.legislatura_id,
            Documento.pdf_url,
        )
        .join(Documento, Votacion.documento_id == Documento.id)
        .where(Votacion.votacion_id == votacion_id)
    ).first()
    return dict(fila._mapping) if fila else None


def contexto_votacion(session: Session, votacion_id: str) -> dict[str, Any] | None:
    return obtener_votacion(session, votacion_id)


def conteo_por_bancada(session: Session, votacion_id: str) -> TableSpec:
    pk = _pk(session, votacion_id)
    if pk is None:
        return TableSpec(titulo=f"Conteo por bancada · {votacion_id}", columnas=[], filas=[])

    filas = session.execute(
        select(
            Congresista.bancada,
            func.sum(case((Voto.posicion == 1, 1), else_=0)).label("si"),
            func.sum(case((Voto.posicion == -1, 1), else_=0)).label("no"),
            func.sum(case((Voto.posicion == 0, 1), else_=0)).label("abst"),
            func.count().label("total"),
        )
        .join(Voto, Voto.congresista_id == Congresista.id)
        .where(Voto.votacion_id == pk)
        .group_by(Congresista.bancada)
        .order_by(func.sum(case((Voto.posicion == 1, 1), else_=0)).desc())
    ).all()

    return TableSpec(
        titulo=f"Conteo por bancada · {votacion_id}",
        columnas=["Bancada", "A favor", "En contra", "Abstención", "Total"],
        filas=[[fila[0] or "SIN BANCADA", fila[1], fila[2], fila[3], fila[4]] for fila in filas],
        metadata={"votacion_id": votacion_id},
    )


def lista_votos(
    session: Session, votacion_id: str, posicion: int | Posicion = Posicion.FAVOR
) -> TableSpec:
    pk = _pk(session, votacion_id)
    if pk is None:
        return TableSpec(titulo=f"Votos · {votacion_id}", columnas=[], filas=[])

    filas = session.execute(
        select(Congresista.nombre, Congresista.bancada, Voto.posicion)
        .join(Voto, Voto.congresista_id == Congresista.id)
        .where(Voto.votacion_id == pk, Voto.posicion == int(posicion))
        .order_by(Congresista.nombre)
    ).all()

    etiqueta = LABEL.get(int(posicion), "Voto")
    return TableSpec(
        titulo=f"{etiqueta} · {votacion_id}",
        columnas=["Congresista", "Bancada", "Voto"],
        filas=[
            [
                fila[0],
                fila[1] or "SIN BANCADA",
                LABEL.get(fila[2], str(fila[2])),
            ]
            for fila in filas
        ],
        metadata={"votacion_id": votacion_id, "posicion": int(posicion)},
    )


def comparar_bancadas(
    session: Session, votacion_id: str, bancada_a: str, bancada_b: str
) -> TableSpec:
    conteo = conteo_por_bancada(session, votacion_id)
    buscadas = {normalize_key(bancada_a), normalize_key(bancada_b)}
    filas = [
        fila
        for fila in conteo.filas
        if normalize_key(str(fila[0])) in buscadas
    ]
    return TableSpec(
        titulo=f"Comparación de bancadas · {votacion_id}",
        columnas=conteo.columnas,
        filas=filas,
        metadata=conteo.metadata,
    )


def historial_congresista(
    session: Session,
    nombre: str,
    legislatura: str | None = None,
    limit: int = 200,
) -> TableSpec:
    clave = normalize_key(nombre)
    congresistas = session.execute(
        select(Congresista.id, Congresista.nombre, Congresista.bancada).where(
            Congresista.nombre_normalizado.contains(clave)
        )
    ).all()
    if not congresistas:
        return TableSpec(titulo=f"Historial de {nombre}", columnas=[], filas=[])

    ids = [fila[0] for fila in congresistas]
    stmt = (
        select(
            Congresista.nombre,
            Congresista.bancada,
            Documento.fecha,
            Documento.acta_id,
            Documento.legislatura_id,
            Votacion.votacion_id,
            Votacion.titulo,
            Votacion.pagina_inicio,
            Voto.posicion,
        )
        .join(Voto, Voto.congresista_id == Congresista.id)
        .join(Votacion, Voto.votacion_id == Votacion.id)
        .join(Documento, Votacion.documento_id == Documento.id)
        .where(Congresista.id.in_(ids))
        .order_by(Documento.fecha.desc())
        .limit(limit)
    )
    if legislatura:
        stmt = stmt.where(Documento.legislatura_id == legislatura)

    filas = session.execute(stmt).all()
    return TableSpec(
        titulo=f"Historial de voto · {nombre}",
        columnas=[
            "Congresista",
            "Bancada",
            "Fecha",
            "Acta",
            "Legislatura",
            "Votación",
            "ID",
            "Página",
            "Voto",
        ],
        filas=[
            [
                fila[0],
                fila[1] or "SIN BANCADA",
                fila[2],
                fila[3],
                fila[4],
                fila[6],
                fila[5],
                fila[7],
                LABEL.get(fila[8], str(fila[8])),
            ]
            for fila in filas
        ],
        metadata={"nombre": nombre, "legislatura": legislatura},
    )


def ausencias_por_votacion(session: Session, votacion_id: str) -> TableSpec:
    """Deriva ausencias: congresistas activos en la legislatura sin fila de voto.

    ``votos_largo_consolidado`` solo registra votos explícitos; la ausencia se
    calcula por complemento y se marca como derivada.
    """

    pk = _pk(session, votacion_id)
    if pk is None:
        return TableSpec(titulo=f"Ausencias · {votacion_id}", columnas=[], filas=[])

    legislatura = session.scalar(
        select(Documento.legislatura_id)
        .join(Votacion, Votacion.documento_id == Documento.id)
        .where(Votacion.id == pk)
    )
    activos = session.execute(
        select(Congresista.id, Congresista.nombre, Congresista.bancada)
        .join(Voto, Voto.congresista_id == Congresista.id)
        .join(Votacion, Voto.votacion_id == Votacion.id)
        .join(Documento, Votacion.documento_id == Documento.id)
        .where(Documento.legislatura_id == legislatura)
        .distinct()
    ).all()
    presentes = set(
        session.scalars(select(Voto.congresista_id).where(Voto.votacion_id == pk)).all()
    )
    filas = [
        [nombre, bancada or "SIN BANCADA"]
        for congresista_id, nombre, bancada in activos
        if congresista_id not in presentes
    ]
    filas.sort(key=lambda fila: str(fila[0]))
    return TableSpec(
        titulo=f"Ausencias derivadas · {votacion_id}",
        columnas=["Congresista", "Bancada"],
        filas=filas,
        metadata={"votacion_id": votacion_id, "derivado": True},
    )


def votaciones_por_tipo(
    session: Session, tipo: str, legislatura: str | None = None, limit: int = 100
) -> TableSpec:
    filtros = Filtros(tipo=tipo, legislatura=legislatura)
    filas = listar_votaciones(session, filtros=filtros, limit=limit)
    return TableSpec(
        titulo=f"Votaciones de tipo {tipo}",
        columnas=["Votación", "Título", "Acta", "Fecha", "Página", "Sí", "No", "Abst."],
        filas=[
            [
                fila["votacion_id"],
                fila["titulo"],
                fila["acta_id"],
                fila["fecha"],
                fila["pagina_inicio"],
                fila["conteo_si"],
                fila["conteo_no"],
                fila["conteo_abstencion"],
            ]
            for fila in filas
        ],
        metadata={"tipo": tipo, "legislatura": legislatura},
    )
