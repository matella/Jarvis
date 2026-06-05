"""Behavioral eval harness — a curated suite of example utterances + their expected routing.

The complement to harness.py (which replays stored *intents* for drift). This pins the deterministic
routing layer: given an utterance, `fastpath_route` decides whether a deterministic handler fires
(weather, a 'show my X' presenter, remember/remind capture, a mail search) or it falls through to
the LLM router ('llm'). That layer is GPU-free and pure, so the whole suite runs in CI as a guard
gate — a misfire (a coding question wrongly grabbed as a presenter, a mail question lost to facts
recall) shows up as a failing case. Full-pipeline answer-quality grading (needs a live model) is a
separate, on-box concern; this is the cheap, always-on net.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.agents.conversation import fastpath_route
from jarvis.eval.cases import CASES, EvalCase


@dataclass(frozen=True)
class CaseResult:
    case: EvalCase
    got: str
    ok: bool


def run(cases: list[EvalCase] = CASES) -> list[CaseResult]:
    """Route every case through the live classifier and record pass/fail."""
    out: list[CaseResult] = []
    for c in cases:
        got = fastpath_route(c.utterance)
        out.append(CaseResult(case=c, got=got, ok=got == c.expect))
    return out


def failures(results: list[CaseResult]) -> list[CaseResult]:
    return [r for r in results if not r.ok]


def score(results: list[CaseResult]) -> dict[str, float | int]:
    """Aggregate pass-rate over a run — the single number to watch across routing changes."""
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
    }


def main() -> int:
    """`python -m jarvis.eval.behavior` → print the report; exit non-zero if any case regressed."""
    results = run()
    s = score(results)
    for r in failures(results):
        print(f"FAIL  {r.case.utterance!r}: expected {r.case.expect}, got {r.got}")
    print(f"\n{s['passed']}/{s['total']} routed correctly ({s['pass_rate'] * 100:.1f}%)")
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
