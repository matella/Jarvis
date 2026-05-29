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
    s = get_settings()
    table = {
        "reasoning": s.model_reasoning,
        "coder": s.model_coder,
        "embedding": s.model_embedding,
    }
    if role not in table:
        raise ValueError(f"unknown model role: {role!r}")
    return table[role]


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


def chat(
    role: str,
    messages: list[dict],
    *,
    correlation_id: str | None = None,
    context_ref: str | None = None,
    format: str | None = None,
) -> dict:
    s = get_settings()
    model = model_for_role(role)
    correlation_id = correlation_id or ids.new_id(ids.CORRELATION)
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
                duration_ms=duration_ms,
                total_duration_ns=resp.get("total_duration"),
                load_duration_ns=resp.get("load_duration"),
                prompt_eval_count=resp.get("prompt_eval_count"),
                eval_count=resp.get("eval_count"),
                context_ref=context_ref,
            )
        )
    return resp


def embed(text: str, *, role: str = "embedding", correlation_id: str | None = None) -> list[float]:
    model = model_for_role(role)
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
    return vector
