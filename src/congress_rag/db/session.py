"""Conexión y sesiones de SQLite."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from congress_rag.config import settings
from congress_rag.db.models import Base


def get_engine(db_path: Path | str | None = None, echo: bool = False) -> Engine:
    path = Path(db_path) if db_path else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", future=True, echo=echo)


def init_db(engine: Engine, reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_session(engine: Engine | None = None) -> Session:
    engine = engine or get_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return factory()
