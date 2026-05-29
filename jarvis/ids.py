"""Prefixed, time-sortable identifiers.

Every boundary row gets a self-describing id: `<prefix>_<ulid>`. The ULID body is
lexicographically time-ordered, so `ORDER BY id` is creation order and range scans
over a causal chain are cheap; the prefix tells you what a row is at a glance in
`trace`/`explain` output.
"""

from __future__ import annotations

from ulid import ULID

# Canonical prefixes. `corr` (correlation chain) and `ctx` (assembled context) are
# refs rather than table PKs but share the scheme.
EVENT = "evt"
INTENT = "int"
EXECUTION = "exec"
SNAPSHOT = "snap"
MEMORY = "mem"
CORRELATION = "corr"
CONTEXT = "ctx"


def new_id(prefix: str) -> str:
    """Return a fresh `<prefix>_<ulid>` identifier."""
    return f"{prefix}_{ULID()}"
