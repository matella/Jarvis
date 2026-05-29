"""Ollama client wrapper.

Thin functions over the official `ollama` client, normalizing responses to plain dicts
(the library returns pydantic objects in newer versions, dicts in older). Kept as
module-level functions so the router — and tests — can call/monkeypatch them directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ollama import Client

from jarvis.config import get_settings


@lru_cache
def get_client() -> Client:
    return Client(host=get_settings().ollama_url)


def _as_dict(obj: Any) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def chat(model: str, messages: list[dict], *, num_ctx: int, keep_alive: str) -> dict:
    return _as_dict(
        get_client().chat(
            model=model, messages=messages, options={"num_ctx": num_ctx}, keep_alive=keep_alive
        )
    )


def embeddings(model: str, text: str) -> list[float]:
    resp = _as_dict(get_client().embeddings(model=model, prompt=text))
    return [float(x) for x in resp["embedding"]]


def ps() -> list[str]:
    """Names of models currently loaded in VRAM."""
    resp = _as_dict(get_client().ps())
    names = [(m.get("model") or m.get("name")) for m in resp.get("models", [])]
    return [n for n in names if n]


def unload(model: str) -> None:
    """Ask Ollama to evict a model now (keep_alive=0). Best-effort."""
    try:
        get_client().generate(model=model, keep_alive=0)
    except Exception:
        pass
