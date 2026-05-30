"""Router unit tests — Ollama client mocked, no GPU/Redis."""

import pytest

import jarvis.models.router as router
from jarvis.models import client as oclient


def test_model_for_role_resolves_and_rejects() -> None:
    assert router.model_for_role("reasoning")
    assert router.model_for_role("embedding")
    with pytest.raises(ValueError):
        router.model_for_role("bogus")


def test_chat_emits_loaded_and_completed(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(router, "_emit", events.append)
    monkeypatch.setattr(oclient, "ps", lambda: [])  # nothing resident yet
    monkeypatch.setattr(oclient, "unload", lambda m: None)
    monkeypatch.setattr(
        oclient, "chat",
        lambda model, messages, *, num_ctx, keep_alive, format=None: {
            "message": {"role": "assistant", "content": "hi"},
            "total_duration": 123, "eval_count": 5,
        },
    )

    resp = router.chat("reasoning", [{"role": "user", "content": "yo"}], context_ref="ctx_abc")
    assert resp["message"]["content"] == "hi"

    types = [e.type for e in events]
    assert "model.loaded" in types
    completed = next(e for e in events if e.type == "inference.completed")
    assert completed.payload["context_ref"] == "ctx_abc"
    assert completed.payload["role"] == "reasoning"
    assert completed.payload["eval_count"] == 5


def test_chat_prepends_persona_system_prompt(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(router, "_emit", lambda e: None)
    monkeypatch.setattr(oclient, "ps", lambda: [])
    monkeypatch.setattr(oclient, "unload", lambda m: None)
    monkeypatch.setattr(
        oclient, "chat",
        lambda model, messages, **k: seen.update(messages=messages)
        or {"message": {"content": "ok"}},
    )
    router.chat("reasoning", [{"role": "user", "content": "yo"}])
    msgs = seen["messages"]
    assert msgs[0]["role"] == "system" and "Jarvis" in msgs[0]["content"]  # persona injected
    assert msgs[1] == {"role": "user", "content": "yo"}


def test_chat_keeps_caller_system_message(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(router, "_emit", lambda e: None)
    monkeypatch.setattr(oclient, "ps", lambda: [])
    monkeypatch.setattr(oclient, "unload", lambda m: None)
    monkeypatch.setattr(
        oclient, "chat",
        lambda model, messages, **k: seen.update(messages=messages)
        or {"message": {"content": "ok"}},
    )
    supplied = [{"role": "system", "content": "custom"}, {"role": "user", "content": "yo"}]
    router.chat("reasoning", supplied)
    assert seen["messages"] == supplied  # not double-prepended


def test_chat_does_not_reemit_loaded_when_resident(monkeypatch) -> None:
    events = []
    model = router.model_for_role("reasoning")
    monkeypatch.setattr(router, "_emit", events.append)
    monkeypatch.setattr(oclient, "ps", lambda: [model])  # already resident
    monkeypatch.setattr(oclient, "unload", lambda m: None)
    monkeypatch.setattr(
        oclient, "chat",
        lambda model, messages, *, num_ctx, keep_alive, format=None: {"message": {"content": "x"}},
    )

    router.chat("reasoning", [{"role": "user", "content": "q"}])
    assert "model.loaded" not in [e.type for e in events]


def test_swap_unloads_other_models(monkeypatch) -> None:
    events, unloaded = [], []
    monkeypatch.setattr(router, "_emit", events.append)
    monkeypatch.setattr(oclient, "ps", lambda: ["someother:latest"])
    monkeypatch.setattr(oclient, "unload", unloaded.append)
    monkeypatch.setattr(
        oclient, "chat",
        lambda model, messages, *, num_ctx, keep_alive, format=None: {"message": {"content": "x"}},
    )

    router.chat("reasoning", [{"role": "user", "content": "q"}])
    assert "someother:latest" in unloaded
    assert any(e.type == "model.unloaded" for e in events)


def test_embed_returns_vector_and_emits(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(router, "_emit", events.append)
    monkeypatch.setattr(oclient, "ps", lambda: [])
    monkeypatch.setattr(oclient, "unload", lambda m: None)
    monkeypatch.setattr(oclient, "embeddings", lambda model, text: [0.1, 0.2, 0.3])

    vec = router.embed("hello")
    assert vec == [0.1, 0.2, 0.3]
    completed = next(e for e in events if e.type == "inference.completed")
    assert completed.payload["role"] == "embedding"
    assert completed.payload["dims"] == 3
