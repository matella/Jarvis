"""Replay-based regression harness — re-run stored contexts, diff against recorded decisions.

`compare` is pure (original vs replayed decision → DriftResult). `replay_intent` reproduces the
exact inputs (`context_ref`) and runs the current model; `run_suite` aggregates drift over recent
proposed intents. Decision drift across a model swap is the signal — not failure on expected
nondeterminism, so confidence wobble alone isn't drift; a changed capability type or target is.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis import db
from jarvis.core.context_store import get_context
from jarvis.intents.repository import get_intent


@dataclass(frozen=True)
class DriftResult:
    intent_id: str
    original_type: str
    replayed_type: str
    type_changed: bool
    target_changed: bool
    confidence_delta: float
    drift: bool  # a *material* change (type or target), not mere confidence wobble


def compare(
    intent_id: str, *, original_type: str, original_target: dict, original_confidence: float,
    replayed_type: str, replayed_target: dict, replayed_confidence: float,
) -> DriftResult:
    type_changed = original_type != replayed_type
    target_changed = original_target != replayed_target
    return DriftResult(
        intent_id=intent_id,
        original_type=original_type, replayed_type=replayed_type,
        type_changed=type_changed, target_changed=target_changed,
        confidence_delta=round(replayed_confidence - original_confidence, 3),
        drift=type_changed or target_changed,
    )


def replay_intent(intent_id: str) -> DriftResult:
    """Re-run the intent's stored context through the current model; diff against the original."""
    from jarvis.agents.infrastructure import _messages, _parse
    from jarvis.models import router

    with db.connect() as conn:
        intent = get_intent(conn, intent_id)
        if intent is None or not intent.context_ref:
            raise ValueError(f"intent {intent_id} missing or has no context_ref")
        ctx = get_context(conn, intent.context_ref)
    if ctx is None:
        raise ValueError(f"no stored context for {intent.context_ref}")

    resp = router.chat(
        "reasoning", _messages(ctx.prompt), context_ref=ctx.context_ref, format="json",
    )
    new = _parse(str(resp["message"]["content"]))
    return compare(
        intent_id,
        original_type=intent.type, original_target=intent.target,
        original_confidence=intent.reasoning.confidence,
        replayed_type=new.type, replayed_target=new.target,
        replayed_confidence=new.confidence,
    )


@dataclass(frozen=True)
class SuiteReport:
    total: int
    drifted: int
    results: list[DriftResult]

    @property
    def drift_rate(self) -> float:
        return round(self.drifted / self.total, 3) if self.total else 0.0


def recent_proposer_intents(limit: int) -> list[str]:
    """Golden-ish cases: recent agent proposals that carry a stored context_ref."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT intent_id FROM intents WHERE context_ref IS NOT NULL "
            "AND requested_by LIKE %s ORDER BY created_at DESC LIMIT %s",
            ("%agent%", limit),
        ).fetchall()
    return [r["intent_id"] for r in rows]


def run_suite(intent_ids: list[str]) -> SuiteReport:
    """Replay each intent; report how many drifted. Errors on one case don't abort the suite."""
    results: list[DriftResult] = []
    for iid in intent_ids:
        try:
            results.append(replay_intent(iid))
        except Exception as exc:  # noqa: BLE001 — a bad case is skipped, not fatal
            print(f"[eval] {iid} skipped: {exc!r}", flush=True)
    drifted = sum(1 for r in results if r.drift)
    return SuiteReport(total=len(results), drifted=drifted, results=results)
