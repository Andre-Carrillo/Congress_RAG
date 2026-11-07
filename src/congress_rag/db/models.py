"""Modelo relacional (SQLite) del corpus de votaciones."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Congresista(Base):
    __tablename__ = "congresistas"

    id: Mapped[int] = mapped_column(primary_key=True)
    congresista_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    nombre_normalizado: Mapped[str] = mapped_column(String(200), index=True)
    grupo_partido: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bancada: Mapped[str | None] = mapped_column(String(200), nullable=True)
    perfil_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    votos: Mapped[list[Voto]] = relationship(back_populates="congresista")


class Legislatura(Base):
    __tablename__ = "legislaturas"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    periodo_anual: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(200))

    documentos: Mapped[list[Documento]] = relationship(back_populates="legislatura")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    acta_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    numero_sesion: Mapped[int | None] = mapped_column(nullable=True)
    fecha: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legislatura_id: Mapped[str] = mapped_column(ForeignKey("legislaturas.id"))
    ruta_texto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    n_paginas: Mapped[int] = mapped_column(default=0)
    hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    legislatura: Mapped[Legislatura] = relationship(back_populates="documentos")
    votaciones: Mapped[list[Votacion]] = relationship(back_populates="documento")


class Votacion(Base):
    __tablename__ = "votaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    votacion_id: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"))
    indice_votacion: Mapped[int | None] = mapped_column(nullable=True)
    pagina_inicio: Mapped[int | None] = mapped_column(nullable=True)
    posicion_inicio: Mapped[int | None] = mapped_column(nullable=True)
    posicion_fin: Mapped[int | None] = mapped_column(nullable=True)
    titulo: Mapped[str] = mapped_column(Text)
    titulo_normalizado: Mapped[str] = mapped_column(Text, index=True)
    tipo: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    conteo_si: Mapped[int] = mapped_column(default=0)
    conteo_no: Mapped[int] = mapped_column(default=0)
    conteo_abstencion: Mapped[int] = mapped_column(default=0)
    declarado_si: Mapped[int] = mapped_column(default=0)
    declarado_no: Mapped[int] = mapped_column(default=0)
    declarado_abstencion: Mapped[int] = mapped_column(default=0)
    conteo_listado: Mapped[int] = mapped_column(default=0)
    origen: Mapped[str] = mapped_column(String(20), default="ushnu")

    documento: Mapped[Documento] = relationship(back_populates="votaciones")
    votos: Mapped[list[Voto]] = relationship(back_populates="votacion")


class Voto(Base):
    __tablename__ = "votos"
    __table_args__ = (
        UniqueConstraint("votacion_id", "congresista_id", name="uq_voto"),
        Index("ix_votos_votacion", "votacion_id"),
        Index("ix_votos_congresista", "congresista_id"),
    )

    votacion_id: Mapped[int] = mapped_column(ForeignKey("votaciones.id"), primary_key=True)
    congresista_id: Mapped[int] = mapped_column(ForeignKey("congresistas.id"), primary_key=True)
    posicion: Mapped[int] = mapped_column(index=True)
    confianza: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fuente_voto: Mapped[str | None] = mapped_column(String(40), nullable=True)

    votacion: Mapped[Votacion] = relationship(back_populates="votos")
    congresista: Mapped[Congresista] = relationship(back_populates="votos")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id"), nullable=True)
    votacion_id: Mapped[int | None] = mapped_column(ForeignKey("votaciones.id"), nullable=True)
    pagina: Mapped[int | None] = mapped_column(nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)
    texto: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
