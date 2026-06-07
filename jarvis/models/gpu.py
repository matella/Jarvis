"""GPU / VRAM occupancy — what models Ollama holds resident, their VRAM, and idle keep-alive state.

Read-only introspection over Ollama's `/api/ps`. On this box the GPU is Ollama-dedicated, so the set
of resident models *is* the VRAM occupancy that matters — answering the operator's swap-awareness
question ("is anything idle being held in VRAM?") that the one-resident-model design is built on.

No `nvidia-smi` needed (the gateway container has no GPU device); Ollama reports `size_vram` +
`expires_at`, which is exactly the model-occupancy truth. Fully fault-tolerant: any failure surfaces
as `reachable() == False` so the presenter says "runtime unreachable" rather than confabulating.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.models import client

_GIB = 1024 ** 3


def _expires_in_s(raw: object) -> int | None:
    """Seconds until Ollama auto-unloads this model (keep-alive countdown), or None if unknown."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0, int((dt - datetime.now(UTC)).total_seconds()))
    except (ValueError, TypeError):
        return None


def resident_models() -> list[dict]:
    """Each model currently in VRAM: name, vram_gib, size_gib, processor (GPU/CPU/GPU+CPU), and
    expires_in_s (seconds until keep-alive eviction). Empty list when the GPU holds nothing."""
    out: list[dict] = []
    for m in client.ps_detail():
        size = float(m.get("size") or 0)
        vram = float(m.get("size_vram") or 0)
        if vram <= 0:
            processor = "CPU"
        elif vram >= size:
            processor = "GPU"
        else:
            processor = "GPU+CPU"  # partially offloaded — the model didn't fully fit
        out.append({
            "model": m.get("model") or m.get("name") or "?",
            "vram_gib": round(vram / _GIB, 2),
            "size_gib": round(size / _GIB, 2),
            "processor": processor,
            "expires_in_s": _expires_in_s(m.get("expires_at")),
        })
    return out


def gpu_status() -> dict:
    """Snapshot of GPU VRAM occupancy: the resident models + total VRAM held. Raises on a runtime
    error (caught by `reachable()` / the presenter)."""
    models = resident_models()
    return {
        "resident": models,
        "model_count": len(models),
        "vram_held_gib": round(sum(m["vram_gib"] for m in models), 2),
    }


def reachable() -> bool:
    """True if the Ollama runtime answers — the presenter's live failure check."""
    try:
        gpu_status()
        return True
    except Exception:  # noqa: BLE001 — any error → unreachable
        return False
