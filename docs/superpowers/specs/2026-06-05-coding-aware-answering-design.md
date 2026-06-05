# Wave 1.0 — Coding-aware answering

Part of the "make Jarvis smarter" program (Wave 0 = the behavioral eval, already shipped). This
milestone makes coding/technical questions answered by the best available coding brain, under a
coding-expert template, grounded in the operator's real environment. No new infrastructure.

## Problem
A coding question today takes one routing inference on the active backend, answered under the
**general** persona with **no environment context**. Gaps: (a) no coding-specialist framing, (b)
no awareness of the operator's actual stack (Python/OS/lib versions), (c) in local mode it's
answered by `qwen3:1.7b` (reasoning) instead of `qwen2.5-coder:7b` (coder).

## Scope (bundled ideas)
- **#1** route coding answers to the best coding brain — coder model when local, Claude when on.
- **#3** a coding-expert prompt template.
- **#6** inject the operator's real environment (Python version, OS, key library versions).
- **#17** per-intent answer format (brief plan → correct/runnable code → caveats).

Deferred to their own milestones: **#5** doc-RAG (needs a doc-ingestion subsystem), **#11/#12/#13**
execute-to-verify (needs a sandboxed runner + a security pass — touches the execution boundary).

## Design
1. **Domain signal (LLM classifies, code decides).** Add `domain` (`general` | `coding`) to
   `_Decision` + `_DECISION_SCHEMA`; the routing prompt sets it. No brittle regex.
2. **Environment block** — new `jarvis/agents/environment.py::environment_block()`: a deterministic,
   cached string of Python version, OS/arch, and a few key library versions (read via
   `importlib.metadata`, best-effort). Pure and unit-testable.
3. **Specialist answer** — new `conversation._code_answer(ctx, memory, utterance, *, facts)`:
   composes the final answer via `sched_chat("coder", …)` under a coding-expert template that
   includes the env block and the #17 format. `role="coder"` → `qwen2.5-coder:7b` when local; when
   the Claude backend is active, `_resolve_backend` sends it to Claude regardless of role.
4. **Wire `_reason`** — when `decision.route == "answer"` and `decision.domain == "coding"`, return
   `_code_answer(...)` instead of using the routing draft. General questions are unchanged (one
   call). Only coding pays the extra specialist pass.

## Cost
Coding questions become 2 inferences (route + specialist); locally that is a 1.7B→7B swap. Accepted:
coding is high-value and infrequent, and the non-coding path is untouched (still one call).

## Testing
- `environment_block()` — pure unit test (contains Python version; stable shape).
- `_code_answer` — unit test with `sched_chat` monkeypatched (uses coder role, includes env + Q).
- `_reason` dispatch — monkeypatch `_decide` to return `domain=coding` → asserts `_code_answer` runs.
- On-box smoke: a real coding question returns a sensible, env-aware answer.
- Behavioral eval unchanged (deterministic layer can't assert an LLM-produced `domain`).

## Hard-rule compliance
One-shot agents (one extra inference, no loop); deterministic boundary untouched (no code execution
in this milestone); one resident model (role-based, swap acknowledged); replay unaffected (the
specialist call logs its own context_ref via the scheduler).
