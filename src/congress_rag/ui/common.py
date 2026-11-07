"""Utilidades compartidas por las páginas de Streamlit."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from congress_rag.config import settings  # noqa: E402
from congress_rag.db.session import get_engine, get_session  # noqa: E402


def db_exists() -> bool:
    return settings.db_path.exists()


def open_session():
    return get_session(get_engine(settings.db_path))
