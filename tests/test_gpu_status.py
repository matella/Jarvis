"""GPU/VRAM occupancy capability — parsing Ollama /api/ps, the presenter, and routing."""

from __future__ import annotations

from jarvis.agents import conversation as convo
from jarvis.models import gpu

_GIB = 1024 ** 3


def test_resident_models_parses_vram_and_processor(monkeypatch) -> None:
    monkeypatch.setattr(gpu.client, "ps_detail", lambda: [
        {"model": "qwen3:4b", "size": int(4.2 * _GIB), "size_vram": int(4.2 * _GIB),
         "expires_at": "2099-01-01T00:00:00Z"},
        {"model": "embed", "size": _GIB, "size_vram": 0},                    # CPU
        {"model": "big", "size": 8 * _GIB, "size_vram": 6 * _GIB},           # partial offload
    ])
    rows = gpu.resident_models()
    assert rows[0]["processor"] == "GPU" and rows[0]["vram_gib"] == 4.2
    assert rows[1]["processor"] == "CPU"
    assert rows[2]["processor"] == "GPU+CPU"
    assert rows[0]["expires_in_s"] and rows[0]["expires_in_s"] > 0  # far-future keep-alive


def test_gpu_status_totals(monkeypatch) -> None:
    monkeypatch.setattr(gpu.client, "ps_detail", lambda: [
        {"model": "a", "size": _GIB, "size_vram": _GIB},
        {"model": "b", "size": 2 * _GIB, "size_vram": 2 * _GIB},
    ])
    st = gpu.gpu_status()
    assert st["model_count"] == 2 and st["vram_held_gib"] == 3.0


def test_present_gpu_idle_when_nothing_resident(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.gpu.reachable", lambda: True)
    monkeypatch.setattr("jarvis.models.gpu.gpu_status",
                        lambda: {"resident": [], "model_count": 0, "vram_held_gib": 0.0})
    out = convo._present_gpu("is anything idle in vram?")
    assert "idle" in out.message.lower() and not out.artifacts


def test_present_gpu_lists_resident_models(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.gpu.reachable", lambda: True)
    monkeypatch.setattr("jarvis.models.gpu.gpu_status", lambda: {
        "resident": [{"model": "qwen3:4b", "vram_gib": 4.2, "size_gib": 4.2,
                      "processor": "GPU", "expires_in_s": 180}],
        "model_count": 1, "vram_held_gib": 4.2})
    out = convo._present_gpu("what's loaded on the gpu?")
    assert out.artifacts and out.artifacts[0].title == "GPU — VRAM occupancy"
    assert "4.2 GB" in out.message


def test_present_gpu_not_reachable(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.gpu.reachable", lambda: False)
    out = convo._present_gpu("gpu status")
    assert "Ollama" in out.message


def test_routing_gpu_questions() -> None:
    for q in ("is anything idle in vram?", "what's loaded on the gpu",
              "gpu status", "how much vram is in use"):
        assert convo.fastpath_route(q) == "present:gpu", q


def test_free_unloads_resident_models(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(gpu, "resident_models",
                        lambda: [{"model": "qwen3:4b"}, {"model": "embed"}])
    monkeypatch.setattr(gpu.client, "unload", lambda m: calls.append(m))
    assert gpu.free() == ["qwen3:4b", "embed"]
    assert calls == ["qwen3:4b", "embed"]


def test_present_gpu_free_command(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.gpu.reachable", lambda: True)
    monkeypatch.setattr("jarvis.models.gpu.free", lambda: ["qwen3:4b"])
    out = convo._present_gpu("free the gpu")
    assert "unloaded qwen3:4b" in out.message and not out.artifacts


def test_present_gpu_free_when_empty(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.models.gpu.reachable", lambda: True)
    monkeypatch.setattr("jarvis.models.gpu.free", lambda: [])
    out = convo._present_gpu("unload the model")
    assert "Nothing to free" in out.message


def test_gpu_telemetry_emits_load_and_evict(monkeypatch) -> None:
    from jarvis.ingest import gpu as gpu_tel

    events: list = []
    monkeypatch.setattr(gpu_tel, "emit_event", lambda e: events.append(e))
    gpu_tel._last = None
    monkeypatch.setattr(gpu_tel.gpu, "resident_models", lambda: [{"model": "qwen3:4b"}])
    assert gpu_tel.sample_models() == 0 and not events       # first tick seeds, no event
    monkeypatch.setattr(gpu_tel.gpu, "resident_models", lambda: [{"model": "coder"}])
    assert gpu_tel.sample_models() == 2                       # qwen evicted + coder loaded
    types = sorted(e.type for e in events)
    assert types == ["model.evicted", "model.loaded"]


def test_gpu_telemetry_silent_when_unchanged(monkeypatch) -> None:
    from jarvis.ingest import gpu as gpu_tel

    gpu_tel._last = {"qwen3:4b"}
    monkeypatch.setattr(gpu_tel, "emit_event", lambda e: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(gpu_tel.gpu, "resident_models", lambda: [{"model": "qwen3:4b"}])
    assert gpu_tel.sample_models() == 0                       # unchanged → no events
