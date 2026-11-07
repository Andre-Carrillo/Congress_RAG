"""Resolución de nombres de congresistas contra el padrón oficial."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from congress_rag.ingestion.normalize import normalize_key


@dataclass
class MatchResult:
    nombre: str | None
    score: float
    candidato: str | None = None


@dataclass
class NameResolver:
    """Resuelve variantes de nombres y alias contra una lista canónica."""

    nombres: list[str] = field(default_factory=list)
    umbral: float = 88.0
    _mapa: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._mapa = {normalize_key(nombre): nombre for nombre in self.nombres}

    def resolve(self, nombre: str) -> MatchResult:
        clave = normalize_key(nombre)
        if not clave:
            return MatchResult(nombre=None, score=0.0)
        if clave in self._mapa:
            return MatchResult(nombre=self._mapa[clave], score=100.0, candidato=self._mapa[clave])

        resultado = process.extractOne(
            clave,
            self._mapa.keys(),
            scorer=fuzz.WRatio,
            score_cutoff=self.umbral,
        )
        if resultado is None:
            return MatchResult(nombre=None, score=0.0)
        _, score, clave_match = resultado
        return MatchResult(
            nombre=self._mapa[clave_match],
            score=float(score),
            candidato=self._mapa[clave_match],
        )
