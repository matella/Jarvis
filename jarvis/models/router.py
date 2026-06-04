"""Model router — thin policy over Ollama, not an LLM.

Resolves a task **role** (reasoning / coder / embedding) to a configured Ollama tag,
enforces **one model resident at a time** (unload others before a call), and serializes all
inference through a process-global semaphore (concurrency = 1) — the 8 GB card can only do
one thing at a time and swaps cost seconds. Every call emits `model.loaded` / `model.unloaded`
/ `inference.completed` events to the spine so swap frequency and latency are observable.
"""

from __future__ import annotations

import threading
import time

from jarvis import ids
from jarvis.config import get_settings
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import get_redis, publish_event
from jarvis.models import client as oclient

# Global: only one inference in flight at a time (telemetry + future GPU scheduler depend on it).
_INFERENCE_SEM = threading.Semaphore(1)


def model_for_role(role: str) -> str:
    if role not in ("reasoning", "coder", "embedding"):
        raise ValueError(f"unknown model role: {role!r}")
    # Honor an operator override (Settings page → system_state), else the config default.
    from jarvis.models.backends.state import cached_model

    return cached_model(role)


def _emit(event: Event) -> None:
    # Telemetry must never break inference.
    try:
        publish_event(get_redis(), event)
    except Exception:
        pass


def _event(event_type: str, model: str, correlation_id: str, **payload: object) -> Event:
    return Event(
        type=event_type,
        severity=Severity.info,
        source="router",
        entity_ref=f"model:{model}",
        occurred_at=utcnow(),
        payload={"model": model, **payload},
        correlation_id=correlation_id,
    )


def _swap_to(model: str, role: str, correlation_id: str) -> set[str]:
    """Unload any other resident model so `model` is the sole occupant. Returns prior set."""
    before = set(oclient.ps())
    for other in before:
        if other != model:
            oclient.unload(other)
            _emit(_event("model.unloaded", other, correlation_id, role=role))
    return before


def _with_persona(messages: list[dict]) -> list[dict]:
    """Prepend the shared Jarvis system prompt so every agent reasons under the same identity/rules.

    Skipped if the caller already supplied a system message. Best-effort — never breaks inference.
    """
    if messages and messages[0].get("role") == "system":
        return messages
    try:
        from jarvis.agents.persona import system_prompt

        return [{"role": "system", "content": system_prompt()}, *messages]
    except Exception:  # noqa: BLE001 — persona is enrichment, not a hard dependency
        return messages


def chat(
    role: str,
    messages: list[dict],
    *,
    correlation_id: str | None = None,
    context_ref: str | None = None,
    format: str | dict | None = None,
) -> dict:
    s = get_settings()
    model = model_for_role(role)
    correlation_id = correlation_id or ids.new_id(ids.CORRELATION)
    messages = _with_persona(messages)
    with _INFERENCE_SEM:
        before = _swap_to(model, role, correlation_id)
        start = time.monotonic()
        resp = oclient.chat(
            model, messages, num_ctx=s.inference_context, keep_alive=s.keep_alive, format=format
        )
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        if model not in before:
            _emit(_event("model.loaded", model, correlation_id, role=role))
        _emit(
            _event(
                "inference.completed", model, correlation_id, role=role,
                backend="local",
                duration_ms=duration_ms,
                total_duration_ns=resp.get("total_duration"),
                load_duration_ns=resp.get("load_duration"),
                prompt_eval_count=resp.get("prompt_eval_count"),
                eval_count=resp.get("eval_count"),
                context_ref=context_ref,
            )
        )
    return resp


def embed_many(
    texts: list[str], *, role: str = "embedding", correlation_id: str | None = None
) -> list[list[float]]:
    """Embed many texts under ONE semaphore hold; emit ONE summary event (no per-item flood)."""
    model = model_for_role(role)
    correlation_id = correlation_id or ids.new_id(ids.CORRELATION)
    with _INFERENCE_SEM:
        before = _swap_to(model, role, correlation_id)
        start = time.monotonic()
        vectors = [oclient.embeddings(model, t) for t in texts]
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        if model not in before:
            _emit(_event("model.loaded", model, correlation_id, role=role))
        _emit(
            _event(
                "inference.completed", model, correlation_id, role=role,
                duration_ms=duration_ms, batch=len(texts),
            )
        )
    return vectors


def embed(text: str, *, role: str = "embedding", correlation_id: str | None = None) -> list[float]:
    model = model_for_role(role)
    # Cost-aware (#8): embeddings are deterministic — a cache hit skips inference entirely.
    from jarvis.models.cache import enabled as cache_enabled
    from jarvis.models.cache import get_cache

    cache = get_cache() if cache_enabled() else None
    if cache is not None:
        hit = cache.get(model, text)
        if hit is not None:
            return hit
    correlation_id = correlation_id or ids.new_id(ids.CORRELATION)
    with _INFERENCE_SEM:
        before = _swap_to(model, role, correlation_id)
        start = time.monotonic()
        vector = oclient.embeddings(model, text)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        if model not in before:
            _emit(_event("model.loaded", model, correlation_id, role=role))
        _emit(
            _event(
                "inference.completed", model, correlation_id, role=role,
                duration_ms=duration_ms, dims=len(vector),
            )
        )
    if cache is not None:
        cache.put(model, text, vector)
    return vector
