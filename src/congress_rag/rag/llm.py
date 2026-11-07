"""Abstracción de proveedores LLM: Ollama local y Gemini."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from congress_rag.config import Settings, settings


class LLMProvider(Protocol):
    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> str | BaseModel: ...

    def name(self) -> str: ...


class OllamaProvider:
    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self.model = model or settings.ollama_model
        self.host = host or settings.ollama_host

    def name(self) -> str:
        return f"ollama:{self.model}"

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> str | BaseModel:
        try:
            import ollama
        except ImportError as exc:  # pragma: no cover - depende de extras
            raise RuntimeError("Falta ollama. Instala con: uv sync --extra llm") from exc

        cliente = ollama.Client(host=self.host)
        argumentos: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0},
        }
        if schema is not None:
            argumentos["format"] = schema.model_json_schema()

        respuesta = cliente.chat(**argumentos)
        contenido = _contenido(respuesta)
        if schema is not None:
            return schema.model_validate_json(contenido)
        return contenido


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY no está configurada en .env")

    def name(self) -> str:
        return f"gemini:{self.model}"

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> str | BaseModel:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depende de extras
            raise RuntimeError("Falta google-genai. Instala con: uv sync --extra llm") from exc

        cliente = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(temperature=0)
        if schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = schema

        respuesta = cliente.models.generate_content(
            model=self.model, contents=prompt, config=config
        )
        texto = getattr(respuesta, "text", None) or ""
        if schema is not None:
            return schema.model_validate_json(texto)
        return texto


def _contenido(respuesta: Any) -> str:
    mensaje = getattr(respuesta, "message", None)
    if mensaje is not None:
        return getattr(mensaje, "content", "") or ""
    if isinstance(respuesta, dict):
        return (respuesta.get("message") or {}).get("content", "")
    return str(respuesta)


def get_provider(cfg: Settings | None = None) -> LLMProvider:
    cfg = cfg or settings
    if cfg.llm_provider.lower() == "gemini":
        return GeminiProvider(cfg.gemini_api_key, cfg.gemini_model)
    return OllamaProvider(cfg.ollama_model, cfg.ollama_host)
