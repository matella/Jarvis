"""Conservative answer cache (#22) — reuse a vetted answer for a repeated, self-contained question.

Only CODING answers go through here: they depend on the (stable) question + environment, not live
homelab state, so serving a repeat from cache is safe — and they're the most expensive path (coder
model + syntax/exec verification). Two guards keep it conservative: context-dependent asks ("fix
this", "the error above") and short fragments are never cached (the same words mean different things
across turns), and entries expire on a short TTL. In-process + LRU-bounded; a redeploy clears it. No
stale-fact risk: live data and operator facts never flow through this path.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict

_TTL_SECONDS = 6 * 3600
_MAX_ENTRIES = 256
_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

# Back-references mean the answer depends on prior turns → not safely reusable by text alone.
_DEMONSTRATIVE_RE = re.compile(
    r"\b(this|that|these|those|above|below|previous|earlier|here|it|"
    r"the (?:error|code|function|snippet|bug|file|output))\b",
    re.I,
)


def _now() -> float:
    return time.monotonic()


def _norm(utterance: str) -> str:
    return " ".join(utterance.lower().split())


def cacheable(utterance: str) -> bool:
    """Self-contained enough to reuse: substantial, and not a back-reference to earlier context."""
    return len(utterance.split()) >= 4 and not _DEMONSTRATIVE_RE.search(utterance)


def get(utterance: str) -> str | None:
    """A fresh cached answer for this question, or None (miss / expired / not cacheable)."""
    if not cacheable(utterance):
        return None
    key = _norm(utterance)
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, message = entry
    if _now() - ts > _TTL_SECONDS:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return message


def put(utterance: str, message: str) -> None:
    """Store a vetted answer (no-op for non-cacheable questions or empty answers)."""
    if not cacheable(utterance) or not message:
        return
    key = _norm(utterance)
    _cache[key] = (_now(), message)
    _cache.move_to_end(key)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)


def clear() -> None:
    _cache.clear()
