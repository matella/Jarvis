"""Pure verification logic — given observed state, decide verified / unverified / inconclusive.

Kept free of I/O so the judgment is unit-testable and deterministic. The runner gathers the inputs
(current container status + count of fresh failure events since the action) and calls these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class VerifyStatus(StrEnum):
    verified = "verified"  # the intended effect held
    unverified = "unverified"  # it did not (still broken / failed again)
    inconclusive = "inconclusive"  # nothing deterministic to check


_RUNNING = {"running", "healthy", "ok", "up"}
_BROKEN = {"exited", "dead", "restarting", "oomkilled", "paused"}


def classify_container_recovery(status: str | None, bad_events_since: int) -> VerifyStatus:
    """A restart/recovery action worked iff the container is running and nothing failed since."""
    s = (status or "").lower()
    if not s:
        return VerifyStatus.inconclusive
    if s in _RUNNING and bad_events_since == 0:
        return VerifyStatus.verified
    if s in _BROKEN or bad_events_since > 0:
        return VerifyStatus.unverified
    return VerifyStatus.inconclusive


def container_target(target: dict[str, Any]) -> str | None:
    """The state entity ref for a container-targeting intent (else None — nothing to verify)."""
    name = target.get("container")
    return f"container:{name}" if isinstance(name, str) and name else None
