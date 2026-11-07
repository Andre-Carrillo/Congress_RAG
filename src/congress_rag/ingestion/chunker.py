"""Construcción de chunks autocontenidos para el índice vectorial."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from congress_rag.config import Settings, settings
from congress_rag.db.models import Chunk, Congresista, Documento, Votacion, Voto
from congress_rag.ingestion.extractor import (
    load_text,
    page_for_offset,
    slice_positions,
)
from congress_rag.ingestion.normalize import clean_acta_text

VENTANA_NARRATIVA = 3500
SOLAPE_NARRATIVA = 400
MIN_CHARS_NARRATIVA = 300


def _nombre_posicion(posicion: int) -> str:
    return {1: "A FAVOR", -1: "EN CONTRA", 0: "ABSTENCIÓN", 2: "NO VOTÓ"}.get(
        posicion, "SIN DATO"
    )


def _agrupar_por_bancada(votos: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    resumen: dict[str, dict[str, int]] = defaultdict(lambda: {"si": 0, "no": 0, "abst": 0})
    for voto in votos:
        bancada = voto.get("bancada") or "SIN BANCADA"
        if voto["posicion"] == 1:
            resumen[bancada]["si"] += 1
        elif voto["posicion"] == -1:
            resumen[bancada]["no"] += 1
        elif voto["posicion"] == 0:
            resumen[bancada]["abst"] += 1
    return dict(resumen)


def render_votacion_chunk(
    *,
    titulo: str,
    acta_id: str,
    numero_sesion: int | None,
    pagina: int | None,
    legislatura: str,
    votos: list[dict[str, Any]],
    texto_bloque: str = "",
    conteo_si: int,
    conteo_no: int,
    conteo_abst: int,
) -> str:
    """Genera un chunk autocontenido: listas, bancadas y extracto del acta."""

    por_posicion: dict[int, list[str]] = defaultdict(list)
    for voto in votos:
        por_posicion[voto["posicion"]].append(voto["nombre"])

    lineas = [
        f"VOTACIÓN: {titulo}",
        f"Acta {acta_id} · Sesión Nº {numero_sesion or '?'} · Página {pagina or '?'}",
        f"Legislatura {legislatura}",
        f"Resultado: {conteo_si} a favor, {conteo_no} en contra, {conteo_abst} abstenciones",
        "",
    ]

    for posicion in (1, -1, 0):
        nombres = sorted(por_posicion.get(posicion, []))
        lineas.append(f"{_nombre_posicion(posicion)} ({len(nombres)}): {', '.join(nombres)}")
        lineas.append("")

    lineas.append("DISTRIBUCIÓN POR BANCADA:")
    for bancada, conteo in sorted(_agrupar_por_bancada(votos).items()):
        lineas.append(
            f"  {bancada}: {conteo['si']} a favor, {conteo['no']} en contra, "
            f"{conteo['abst']} abstenciones"
        )

    if texto_bloque.strip():
        lineas.extend(["", "EXTRACTO DEL ACTA:", texto_bloque.strip()])

    return "\n".join(lineas)


def _cargar_votos_por_votacion(session: Session) -> dict[int, list[dict[str, Any]]]:
    filas = session.execute(
        select(
            Voto.votacion_id,
            Congresista.nombre,
            Congresista.bancada,
            Voto.posicion,
        )
        .join(Congresista, Voto.congresista_id == Congresista.id)
        .order_by(Congresista.nombre)
    ).all()

    resultado: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for votacion_pk, nombre, bancada, posicion in filas:
        resultado[votacion_pk].append(
            {"nombre": nombre, "bancada": bancada, "posicion": posicion}
        )
    return dict(resultado)


def _chunks_narrativos(
    texto: str,
    *,
    acta_id: str,
    documento_pk: int,
    legislatura: str,
    intervalos: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    inicio = 0
    indice = 0
    longitud = len(texto)

    def intersecta(a: int, b: int) -> bool:
        return any(a < fin and b > comienzo for comienzo, fin in intervalos)

    while inicio < longitud:
        fin = min(longitud, inicio + VENTANA_NARRATIVA)
        if not intersecta(inicio, fin):
            fragmento = clean_acta_text(texto[inicio:fin])
            if len(fragmento) >= MIN_CHARS_NARRATIVA:
                pagina = page_for_offset(texto, inicio)
                chunks.append(
                    {
                        "id": f"nar-{acta_id}-{indice:04d}",
                        "texto": fragmento,
                        "metadata": {
                            "legislatura_id": legislatura,
                            "acta_id": acta_id,
                            "pagina": pagina,
                            "tipo": "narrativa",
                            "votacion_id": "",
                            "anio": int(acta_id[:4]) if acta_id[:4].isdigit() else 0,
                            "documento_id": documento_pk,
                        },
                    }
                )
                indice += 1
        if fin >= longitud:
            break
        inicio = fin - SOLAPE_NARRATIVA

    return chunks


def construir_chunks(session: Session, cfg: Settings | None = None) -> int:
    cfg = cfg or settings
    cfg.ensure_dirs()

    filas = session.execute(
        select(
            Votacion.id,
            Votacion.votacion_id,
            Votacion.titulo,
            Votacion.pagina_inicio,
            Votacion.posicion_inicio,
            Votacion.posicion_fin,
            Votacion.conteo_si,
            Votacion.conteo_no,
            Votacion.conteo_abstencion,
            Documento.id,
            Documento.acta_id,
            Documento.numero_sesion,
            Documento.ruta_texto,
            Documento.legislatura_id,
        )
        .join(Documento, Votacion.documento_id == Documento.id)
        .order_by(Votacion.votacion_id)
    ).all()

    votos_por_votacion = _cargar_votos_por_votacion(session)
    textos: dict[str, str] = {}
    intervalos_por_documento: dict[int, list[tuple[int, int]]] = defaultdict(list)
    chunks: list[dict[str, Any]] = []

    for (
        votacion_pk,
        votacion_id,
        titulo,
        pagina,
        pos_inicio,
        pos_fin,
        conteo_si,
        conteo_no,
        conteo_abst,
        documento_pk,
        acta_id,
        numero_sesion,
        ruta_texto,
        legislatura,
    ) in filas:
        texto = textos.get(acta_id)
        if texto is None and ruta_texto:
            ruta = Path(ruta_texto)
            texto = load_text(ruta) if ruta.exists() else ""
            textos[acta_id] = texto

        if pos_inicio is not None and pos_fin is not None:
            intervalos_por_documento[documento_pk].append((pos_inicio, pos_fin))

        bloque = clean_acta_text(slice_positions(texto or "", pos_inicio, pos_fin))
        cuerpo = render_votacion_chunk(
            titulo=titulo,
            acta_id=acta_id,
            numero_sesion=numero_sesion,
            pagina=pagina,
            legislatura=legislatura,
            votos=votos_por_votacion.get(votacion_pk, []),
            texto_bloque=bloque,
            conteo_si=conteo_si,
            conteo_no=conteo_no,
            conteo_abst=conteo_abst,
        )
        chunks.append(
            {
                "id": f"vot-{votacion_id}",
                "texto": cuerpo,
                "_votacion_pk": votacion_pk,
                "metadata": {
                    "legislatura_id": legislatura,
                    "acta_id": acta_id,
                    "pagina": pagina or 1,
                    "tipo": "votacion",
                    "votacion_id": votacion_id,
                    "anio": int(acta_id[:4]) if acta_id[:4].isdigit() else 0,
                    "documento_id": documento_pk,
                },
            }
        )

    documentos = session.execute(
        select(Documento.acta_id, Documento.id, Documento.ruta_texto, Documento.legislatura_id)
    ).all()
    for acta_id, documento_pk, ruta_texto, legislatura in documentos:
        if not ruta_texto or not Path(ruta_texto).exists():
            continue
        texto = load_text(Path(ruta_texto))
        chunks.extend(
            _chunks_narrativos(
                texto,
                acta_id=acta_id,
                documento_pk=documento_pk,
                legislatura=legislatura,
                intervalos=intervalos_por_documento.get(documento_pk, []),
            )
        )

    with cfg.chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    session.execute(delete(Chunk))
    session.bulk_insert_mappings(
        Chunk,
        [
            {
                "id": chunk["id"],
                "documento_id": chunk["metadata"].get("documento_id"),
                "votacion_id": chunk.get("_votacion_pk"),
                "pagina": chunk["metadata"].get("pagina"),
                "tipo": chunk["metadata"].get("tipo"),
                "texto": chunk["texto"],
                "metadata_json": json.dumps(chunk["metadata"], ensure_ascii=False),
            }
            for chunk in chunks
        ],
    )
    session.commit()
    return len(chunks)
