"""Configuración central del proyecto, cargada desde `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Corpus y rutas
    ushnu_dir: Path = Path.home() / "Documents/dev/ushnu-congreso"
    legacy_dir: Path = Path.home() / "Documents/dev/Congress_Analysis"
    data_dir: Path = PROJECT_ROOT / "data"
    db_path: Path = PROJECT_ROOT / "data/processed/congress.db"
    chroma_dir: Path = PROJECT_ROOT / "data/chroma"
    chunks_path: Path = PROJECT_ROOT / "data/processed/chunks.jsonl"
    qa_report_path: Path = PROJECT_ROOT / "data/processed/qa_report.csv"

    # Alcance
    legislaturas: str = "2025-2026-L1,2025-2026-L2"

    # LLM
    llm_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Recuperación
    embedding_model: str = "intfloat/multilingual-e5-small"
    top_k: int = 5
    min_score: float = 0.25

    def model_post_init(self, __context: object, /) -> None:
        for name in ("data_dir", "db_path", "chroma_dir", "chunks_path", "qa_report_path"):
            value = getattr(self, name)
            if not value.is_absolute():
                setattr(self, name, PROJECT_ROOT / value)

    @property
    def legislaturas_list(self) -> list[str]:
        return [item.strip() for item in self.legislaturas.split(",") if item.strip()]

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chunks_path.parent.mkdir(parents=True, exist_ok=True)
        self.qa_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
