"""Operational mode state machine — governs how autonomous Jarvis is allowed to be.

One persisted, runtime-settable mode drives a single `decide()` policy that the execution gate
and the ambient reactor both consult. The ladder of autonomy:

- observe (default): propose only; execution is a dry-run (never touches infrastructure).
- approval_required: real execution, but ONLY for human-approved intents (all of them).
- semi_autonomous: low-risk + reversible intents are auto-approved AND executed unattended;
  anything higher-risk still requires human approval.
- maintenance: a freeze — no execution at all, and the reactor is suspended.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import psycopg

from jarvis.config import get_settings
from jarvis.intents.models import Intent, Risk


class Mode(StrEnum):
    observe = "observe"
    approval_required = "approval_required"
    semi_autonomous = "semi_autonomous"
    maintenance = "maintenance"


@dataclass(frozen=True)
class Decision:
    blocked: bool = False         # maintenance: refuse execution outright
    dry_run: bool = False         # observe: record a skipped execution, touch nothing
    auto_approve: bool = False    # semi_autonomous + auto-safe: approve without a human
    force_approval: bool = False  # require human approval even if the intent didn't ask for it


def _auto_safe(intent: Intent) -> bool:
    """Low-risk AND reversible — the only intents semi_autonomous runs unattended."""
    return intent.reasoning.risk is Risk.low and intent.reasoning.reversible


def decide(mode: Mode, intent: Intent) -> Decision:
    if mode is Mode.maintenance:
        return Decision(blocked=True)
    if mode is Mode.observe:
        return Decision(dry_run=True)
    if mode is Mode.approval_required:
        return Decision(force_approval=True)
    if mode is Mode.semi_autonomous:
        return Decision(auto_approve=True) if _auto_safe(intent) else Decision(force_approval=True)
    return Decision(dry_run=True)  # unknown mode → safest


def get_mode(conn: psycopg.Connection) -> Mode:
    row = conn.execute("SELECT value FROM system_state WHERE key = 'mode'").fetchone()
    if row is not None:
        return Mode(row["value"])
    return Mode(get_settings().jarvis_mode)  # default from config when unset


def set_mode(conn: psycopg.Connection, mode: Mode) -> None:
    conn.execute(
        "INSERT INTO system_state (key, value, updated_at) VALUES ('mode', %s, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (mode.value,),
    )
