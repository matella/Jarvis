"""Pure backend resolution — precedence + hard overrides. No I/O; fully unit-tested.

Precedence: explicit per-call > per-routine > global default > "local". Hard overrides force
"local" (the always-on safety net): circuit breaker open, daily budget exhausted, or a
grammar-constrained (schema) call that wasn't *explicitly* sent to claude.
"""

from __future__ import annotations

from typing import Literal

Backend = Literal["local", "claude"]


def resolve_backend(
    explicit: Backend | None,
    routine: Backend | None,
    global_default: Backend | None,
    *,
    has_schema: bool,
    breaker_open: bool,
    budget_exhausted: bool,
) -> Backend:
    if breaker_open or budget_exhausted:
        return "local"
    chosen: Backend = explicit or routine or global_default or "local"
    if chosen == "claude" and has_schema and explicit != "claude":
        # Grammar-constrained decode belongs on local unless the caller deliberately chose claude.
        return "local"
    return chosen
