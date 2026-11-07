"""Carga del corpus consolidado de ``ushnu-congreso`` a SQLite."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from congress_rag.config import Settings, settings
from congress_rag.db.models import (
    Chunk,
    Congresista,
    Documento,
    Legislatura,
    Votacion,
    Voto,
)
from congress_rag.db.session import init_db
from congress_rag.ingestion.extractor import split_pages
from congress_rag.ingestion.normalize import normalize_key, normalize_title
from congress_rag.schemas import IngestStats

ENCODING = "utf-8-sig"


@dataclass
class LegacyData:
    rows: list[dict[str, Any]] = field(default_factory=list)
    archivos: dict[str, str] = field(default_factory=dict)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding=ENCODING, dtype=str, keep_default_na=False)


def clasificar_tipo(titulo: str) -> str:
    titulo_upper = titulo.upper()
    reglas = [
        ("MOCIÓN", "moción"),
        ("MOCION", "moción"),
        ("CUESTIÓN PREVIA", "cuestión previa"),
        ("CUESTION PREVIA", "cuestión previa"),
        ("RECONSIDERACIÓN", "reconsideración"),
        ("RECONSIDERACION", "reconsideración"),
        ("INSISTENCIA", "insistencia"),
        ("EXONERACIÓN", "exoneración"),
        ("EXONERACION", "exoneración"),
        ("ELECCIÓN", "elección"),
        ("ELECCION", "elección"),
        ("COMISIÓN", "comisión"),
        ("COMISION", "comisión"),
        ("RESOLUCIÓN LEGISLATIVA", "resolución legislativa"),
        ("RESOLUCION LEGISLATIVA", "resolución legislativa"),
        ("PROYECTO", "proyecto"),
    ]
    for needle, tipo in reglas:
        if needle in titulo_upper:
            return tipo
    return "otro"


def cargar_legislaturas(ushnu_dir: Path, legislaturas: list[str]) -> list[dict[str, Any]]:
    sesiones = _read_csv(ushnu_dir / "datos/publicos/sesiones.csv")
    sesiones = sesiones[sesiones["legislatura_codigo"].isin(legislaturas)]
    rows: list[dict[str, Any]] = []
    for codigo, grupo in sesiones.groupby("legislatura_codigo", sort=False):
        primera = grupo.iloc[0]
        rows.append(
            {
                "id": codigo,
                "periodo_anual": primera["periodo_anual"],
                "nombre": primera["legislatura"],
            }
        )
    return rows


def cargar_congresistas(ushnu_dir: Path) -> list[dict[str, Any]]:
    oficiales = _read_csv(ushnu_dir / "datos/publicos/congresistas_oficiales_actuales.csv")
    bancadas_path = ushnu_dir / "datos/publicos/bancadas_resueltas_general.csv"
    bancadas = _read_csv(bancadas_path) if bancadas_path.exists() else pd.DataFrame()

    mapa_bancada: dict[str, str] = {}
    if not bancadas.empty and "congresista_id_oficial" in bancadas.columns:
        orden = bancadas.copy()
        if "fecha_ultimo_evento" in orden.columns:
            orden = orden.sort_values("fecha_ultimo_evento")
        orden = orden.drop_duplicates(subset=["congresista_id_oficial"], keep="last")
        mapa_bancada = {
            row["congresista_id_oficial"]: row.get("bancada_nombre") or ""
            for _, row in orden.iterrows()
        }

    rows: list[dict[str, Any]] = []
    for _, row in oficiales.iterrows():
        cid = row["congresista_id"]
        nombre = row["nombre_completo"]
        rows.append(
            {
                "congresista_id": cid,
                "nombre": nombre,
                "nombre_normalizado": normalize_key(nombre),
                "grupo_partido": row.get("grupo_parlamentario_actual") or None,
                "bancada": mapa_bancada.get(cid) or row.get("grupo_parlamentario_actual") or None,
                "perfil_url": row.get("perfil_url") or None,
            }
        )
    return rows


def cargar_documentos(
    ushnu_dir: Path, legislaturas: list[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    sesiones = _read_csv(ushnu_dir / "datos/publicos/sesiones.csv")
    sesiones = sesiones[sesiones["legislatura_codigo"].isin(legislaturas)].copy()

    extraccion_path = ushnu_dir / "datos/publicos/registro_extraccion.csv"
    extraccion = _read_csv(extraccion_path) if extraccion_path.exists() else pd.DataFrame()
    mapa_extraccion = (
        extraccion.set_index("acta_id").to_dict("index") if not extraccion.empty else {}
    )

    rows: list[dict[str, Any]] = []
    for _, row in sesiones.iterrows():
        acta_id = row["acta_id"]
        ruta = ushnu_dir / (row.get("ruta_texto") or f"datos/procesados/texto/{acta_id}.txt")
        n_paginas = 0
        if ruta.exists():
            n_paginas = len(split_pages(ruta.read_text(encoding="utf-8")))
        extra = mapa_extraccion.get(acta_id, {})
        rows.append(
            {
                "acta_id": acta_id,
                "numero_sesion": int(row["numero_sesion"]) if row.get("numero_sesion") else None,
                "fecha": row.get("fecha") or None,
                "legislatura_id": row["legislatura_codigo"],
                "ruta_texto": str(ruta),
                "pdf_url": extra.get("pdf_url") or None,
                "n_paginas": n_paginas,
                "hash_sha256": extra.get("pdf_sha256") or None,
            }
        )
    return rows, set(sesiones["acta_id"].tolist())


def cargar_votaciones(ushnu_dir: Path, acta_ids: set[str]) -> list[dict[str, Any]]:
    votaciones = _read_csv(ushnu_dir / "datos/publicos/votaciones.csv")
    votaciones = votaciones[votaciones["acta_id"].isin(acta_ids)]

    rows: list[dict[str, Any]] = []
    for _, row in votaciones.iterrows():
        titulo = normalize_title(row["titulo_votacion"])
        rows.append(
            {
                "votacion_id": row["votacion_id"],
                "acta_id": row["acta_id"],
                "indice_votacion": int(row["indice_votacion"])
                if row.get("indice_votacion")
                else None,
                "pagina_inicio": int(row["pagina_inicio"]) if row.get("pagina_inicio") else None,
                "posicion_inicio": int(row["posicion_inicio"])
                if row.get("posicion_inicio")
                else None,
                "posicion_fin": int(row["posicion_fin"]) if row.get("posicion_fin") else None,
                "titulo": titulo,
                "titulo_normalizado": normalize_key(titulo),
                "tipo": clasificar_tipo(titulo),
                "conteo_si": int(row.get("conteo_si") or 0),
                "conteo_no": int(row.get("conteo_no") or 0),
                "conteo_abstencion": int(row.get("conteo_abstencion") or 0),
                "declarado_si": int(row.get("conteo_si") or 0),
                "declarado_no": int(row.get("conteo_no") or 0),
                "declarado_abstencion": int(row.get("conteo_abstencion") or 0),
                "conteo_listado": int(row.get("conteo_total_explicitamente_listado") or 0),
                "origen": "ushnu",
            }
        )
    return rows


def _posicion(valor: str) -> int:
    valor = (valor or "").strip().lower()
    return {"si": 1, "sí": 1, "no": -1, "abstencion": 0, "abstención": 0}.get(valor, 2)


def cargar_votos(
    ushnu_dir: Path,
    votacion_ids: set[str],
    congresistas_por_clave: dict[str, int],
) -> tuple[list[dict[str, Any]], int]:
    path = ushnu_dir / "datos/publicos/votos_largo_consolidado.csv"
    rows: list[dict[str, Any]] = []
    sin_match: set[str] = set()

    for chunk in pd.read_csv(path, encoding=ENCODING, dtype=str, chunksize=100_000):
        chunk = chunk[chunk["votacion_id"].isin(votacion_ids)]
        for _, row in chunk.iterrows():
            clave = normalize_key(row["congresista_raw"])
            congresista_id = congresistas_por_clave.get(clave)
            if congresista_id is None:
                sin_match.add(row["congresista_raw"])
                continue
            rows.append(
                {
                    "votacion_id": row["votacion_id"],
                    "congresista_id": congresista_id,
                    "posicion": _posicion(row["voto_normalizado"]),
                    "confianza": row.get("confianza") or None,
                    "fuente_voto": row.get("fuente_voto") or None,
                }
            )
    return rows, len(sin_match)


def _listar_legacy(legacy_dir: Path, cantidad: int) -> list[Path]:
    carpeta = legacy_dir / "votos_csv"
    if not carpeta.exists():
        return []
    archivos: list[tuple[int, int, Path]] = []
    for path in carpeta.glob("*.csv"):
        try:
            mayor, menor = (int(part) for part in path.stem.split("."))
        except ValueError:
            continue
        with path.open(encoding=ENCODING) as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                continue
        if len(header) <= 1:
            continue
        archivos.append((mayor, menor, path))
    archivos.sort()
    return [path for _, _, path in archivos[-cantidad:]]


def _leer_legacy(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding=ENCODING, newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        titulos = header[1:]
        conteos = [{"si": 0, "no": 0, "abst": 0, "ausente": 0} for _ in titulos]
        for fila in reader:
            for indice, valor in enumerate(fila[1:]):
                if indice >= len(conteos):
                    break
                try:
                    numero = int(valor)
                except (TypeError, ValueError):
                    continue
                if numero == 1:
                    conteos[indice]["si"] += 1
                elif numero == -1:
                    conteos[indice]["no"] += 1
                elif numero == 0:
                    conteos[indice]["abst"] += 1
                elif numero == 2:
                    conteos[indice]["ausente"] += 1

    return [
        {
            "titulo": titulo,
            "legacy_si": conteo["si"],
            "legacy_no": conteo["no"],
            "legacy_abst": conteo["abst"],
            "legacy_ausente": conteo["ausente"],
        }
        for titulo, conteo in zip(titulos, conteos, strict=False)
    ]


def cargar_legacy(legacy_dir: Path, legislaturas: list[str]) -> LegacyData:
    archivos = _listar_legacy(legacy_dir, len(legislaturas))
    data = LegacyData(archivos={})
    for legislatura, path in zip(legislaturas, archivos, strict=False):
        data.archivos[legislatura] = path.name
        for fila in _leer_legacy(path):
            fila["legislatura"] = legislatura
            data.rows.append(fila)
    return data


def bootstrap(session: Session, cfg: Settings | None = None) -> IngestStats:
    cfg = cfg or settings
    cfg.ensure_dirs()
    engine = session.get_bind()
    init_db(engine, reset=True)

    stats = IngestStats()

    legislaturas = cargar_legislaturas(cfg.ushnu_dir, cfg.legislaturas_list)
    session.add_all(
        [
            Legislatura(id=row["id"], periodo_anual=row["periodo_anual"], nombre=row["nombre"])
            for row in legislaturas
        ]
    )
    session.flush()

    congresistas = cargar_congresistas(cfg.ushnu_dir)
    session.add_all([Congresista(**row) for row in congresistas])
    session.flush()
    stats.congresistas = len(congresistas)

    documentos, acta_ids = cargar_documentos(cfg.ushnu_dir, cfg.legislaturas_list)
    session.add_all([Documento(**row) for row in documentos])
    session.flush()
    stats.documentos = len(documentos)

    mapa_documentos = dict(session.execute(select(Documento.acta_id, Documento.id)).all())
    votaciones = cargar_votaciones(cfg.ushnu_dir, acta_ids)
    session.add_all(
        [
            Votacion(
                **{clave: valor for clave, valor in row.items() if clave != "acta_id"},
                documento_id=mapa_documentos[row["acta_id"]],
            )
            for row in votaciones
        ]
    )
    session.flush()
    stats.votaciones = len(votaciones)

    congresistas_por_clave = {
        nombre_normalizado: congresista_pk
        for congresista_pk, nombre_normalizado in session.execute(
            select(Congresista.id, Congresista.nombre_normalizado)
        ).all()
    }
    mapa_votaciones = dict(
        session.execute(select(Votacion.votacion_id, Votacion.id)).all()
    )

    votos, _sin_match = cargar_votos(cfg.ushnu_dir, set(mapa_votaciones), congresistas_por_clave)
    votos_db: dict[tuple[int, int], dict[str, Any]] = {}
    for row in votos:
        votos_db[(mapa_votaciones[row["votacion_id"]], row["congresista_id"])] = {
            "votacion_id": mapa_votaciones[row["votacion_id"]],
            "congresista_id": row["congresista_id"],
            "posicion": row["posicion"],
            "confianza": row["confianza"],
            "fuente_voto": row["fuente_voto"],
        }
    session.bulk_insert_mappings(Voto, list(votos_db.values()))
    session.flush()

    # ``conteo_*`` refleja lo efectivamente consolidado; lo declarado en el
    # registro digital original queda en ``declarado_*`` para el reporte QA.
    agregados: dict[int, dict[int, int]] = defaultdict(lambda: {1: 0, -1: 0, 0: 0})
    for votacion_pk, posicion, cantidad in session.execute(
        select(Voto.votacion_id, Voto.posicion, func.count())
        .where(Voto.posicion.in_([1, -1, 0]))
        .group_by(Voto.votacion_id, Voto.posicion)
    ).all():
        agregados[votacion_pk][int(posicion)] = int(cantidad)

    for votacion_pk, conteos in agregados.items():
        session.execute(
            update(Votacion)
            .where(Votacion.id == votacion_pk)
            .values(
                conteo_si=conteos[1],
                conteo_no=conteos[-1],
                conteo_abstencion=conteos[0],
            )
        )

    session.commit()
    stats.votos = len(votos_db)
    return stats


def construir_reporte_calidad(
    session: Session, legacy: LegacyData, cfg: Settings | None = None
) -> pd.DataFrame:
    cfg = cfg or settings

    votaciones = session.execute(
        select(
            Votacion.id,
            Votacion.votacion_id,
            Votacion.titulo,
            Votacion.titulo_normalizado,
            Votacion.tipo,
            Votacion.declarado_si,
            Votacion.declarado_no,
            Votacion.declarado_abstencion,
            Votacion.pagina_inicio,
            Documento.acta_id,
            Documento.legislatura_id,
        )
        .join(Documento, Votacion.documento_id == Documento.id)
        .order_by(Votacion.votacion_id)
    ).all()

    agregados: dict[int, dict[str, int]] = defaultdict(lambda: {"si": 0, "no": 0, "abst": 0})
    for votacion_pk, posicion, cantidad in session.execute(
        select(Voto.votacion_id, Voto.posicion, func.count()).group_by(
            Voto.votacion_id, Voto.posicion
        )
    ).all():
        clave = (
            "si"
            if posicion == 1
            else "no"
            if posicion == -1
            else "abst"
            if posicion == 0
            else None
        )
        if clave:
            agregados[votacion_pk][clave] = cantidad

    confianza: dict[int, tuple[int, int]] = {}
    for votacion_pk, alta, total in session.execute(
        select(
            Voto.votacion_id,
            func.sum(func.iif(Voto.confianza == "alta", 1, 0)),
            func.count(),
        ).group_by(Voto.votacion_id)
    ).all():
        confianza[votacion_pk] = (int(alta or 0), int(total or 0))

    legacy_por_clave = {
        (row["legislatura"], normalize_key(row["titulo"])): row for row in legacy.rows
    }

    filas: list[dict[str, Any]] = []
    for (
        votacion_pk,
        votacion_id_str,
        titulo,
        titulo_norm,
        tipo,
        c_si,
        c_no,
        c_abst,
        pagina,
        acta_id,
        legislatura,
    ) in votaciones:
        extra = agregados.get(votacion_pk, {"si": 0, "no": 0, "abst": 0})
        legacy_row = legacy_por_clave.get((legislatura, titulo_norm))
        alta, total = confianza.get(votacion_pk, (0, 0))

        declarado = (c_si, c_no, c_abst)
        extraido = (extra["si"], extra["no"], extra["abst"])
        deltas = tuple(e - d for d, e in zip(declarado, extraido, strict=True))

        if total == 0:
            estado = "sin_votos"
        elif sum(deltas) < 0:
            estado = "discrepancia_conteo"
        elif all(delta >= 0 for delta in deltas) and any(delta > 0 for delta in deltas):
            # El consolidado recupera votos vía subsanaciones posteriores.
            estado = "recuperado_subsanacion"
        elif deltas == (0, 0, 0):
            estado = "ok"
        else:
            # El total no baja, pero alguna posición se redistribuyó.
            estado = "ajuste_por_subsanacion"

        filas.append(
            {
                "votacion_id": votacion_id_str,
                "acta_id": acta_id,
                "legislatura": legislatura,
                "pagina": pagina,
                "titulo": titulo,
                "tipo": tipo,
                "conteo_si": c_si,
                "conteo_no": c_no,
                "conteo_abst": c_abst,
                "extraido_si": extra["si"],
                "extraido_no": extra["no"],
                "extraido_abst": extra["abst"],
                "delta_si": deltas[0],
                "delta_no": deltas[1],
                "delta_abst": deltas[2],
                "recuperados": sum(deltas),
                "legacy_encontrado": legacy_row is not None,
                "legacy_si": legacy_row["legacy_si"] if legacy_row else None,
                "legacy_no": legacy_row["legacy_no"] if legacy_row else None,
                "legacy_abst": legacy_row["legacy_abst"] if legacy_row else None,
                "confianza_alta": alta,
                "confianza_total": total,
                "confianza_alta_pct": round(alta / total * 100, 2) if total else 0.0,
                "estado": estado,
            }
        )

    df = pd.DataFrame(filas)
    df.to_csv(cfg.qa_report_path, index=False, encoding="utf-8-sig")
    return df


def limpiar_tablas(session: Session) -> None:
    for modelo in (Chunk, Voto, Votacion, Documento, Congresista, Legislatura):
        session.execute(delete(modelo))
    session.commit()
