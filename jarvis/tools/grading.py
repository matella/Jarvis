"""Graduated execution gate (foundation Evolution #2 — refines Hard Rule #1).

Hard Rule #1 is preserved: an LLM never touches infrastructure; the only path is
`LLM → Intent → schema/capability validation → deterministic executor`. What this module grades is
the *human-confirmation* step on that path, by the intent's own contract — **not** the boundary.

- **Auto-run** (no confirmation): low-risk **and** reversible **and** no side effects **and** stays
  on the box (not external). These are the personal-data CRUD writes — create/edit/delete/complete a
  note, task, recipe, document, local calendar event. The operator clicking in the UI is the human;
  Jarvis proposing the same intent rides the same low-risk/reversible path.
- **Gated** (human confirms): anything irreversible, side-effecting, or external — send email,
  request a movie, control Home Assistant, restart a container, run deep research (spends egress +
  budget), start/apply a code session.

This is only the *default* gate for an intent. A tool may always force a gate by marking itself
`external=True` (e.g. `research.run` has no on-box side effects yet reaches the web → gated).

The operational **mode ladder** (`core/modes.py`) still overrides everything at execution time:
`observe` → dry-run (touch nothing), `maintenance` → blocked, `approval_required` → always human,
`semi_autonomous` → auto-approve **and** run the auto-safe (low-risk+reversible) intents unattended.
So to *use* the personal-OS modules unattended, run in `semi_autonomous`; `observe` stays a watcher.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.intents.models import Risk


@dataclass(frozen=True)
class Gate:
    """The gate fields an Intent should carry, derived from a tool's contract characteristics."""

    requires_approval: bool
    risk: Risk
    reversible: bool

    @property
    def auto_run(self) -> bool:
        return not self.requires_approval


def grade(
    *,
    side_effects: bool,
    reversible: bool,
    risk: Risk = Risk.low,
    external: bool = False,
) -> Gate:
    """Default gate for a module tool. Auto-runs iff low-risk AND reversible AND no side effects AND
    on-box (not external); otherwise requires human approval. The mode ladder still overrides."""
    auto = (risk is Risk.low) and reversible and (not side_effects) and (not external)
    return Gate(requires_approval=not auto, risk=risk, reversible=reversible)
