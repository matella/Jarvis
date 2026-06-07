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
