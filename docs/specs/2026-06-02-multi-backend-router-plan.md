# Multi-Backend LLM Router — Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, commit per task. Steps use `- [ ]` checkboxes.
> Spec: `docs/specs/2026-06-02-multi-backend-router.md`. Foundation: `…-personal-os-foundation.md`.

**Goal:** Add an opt-in `claude` reasoning backend (`claude -p`, owner subscription) behind the
existing `scheduler.chat` switch point, defaulting to `local` (Ollama) so Jarvis never goes dark.

**Architecture:** Dispatch fork lives in `scheduler.chat`, **above** the GPU semaphore. `local` →
today's path untouched; `claude` → `claude_backend` directly (off-GPU), schema-validated with
fallback to `local`. Auth = `CLAUDE_CODE_OAUTH_TOKEN` env var (spike-verified). Pilot: chat (local
routes / Claude composes) + the postmortem routine.

**Tech Stack:** Python 3.11, Pydantic-settings, Ollama client, `claude` CLI (Node, in the image),
Postgres `system_state`, pytest. Conventions: `from __future__ import annotations`, type hints,
ruff (100-col), `./.venv/bin/python -m pytest`, `./.venv/bin/ruff check`.

---

## File structure

| File | Responsibility |
|---|---|
| `jarvis/models/backends/__init__.py` | package marker |
| `jarvis/models/backends/resolve.py` | **pure** `resolve_backend(...)` — precedence + hard overrides |
| `jarvis/models/backends/availability.py` | `claude_available()` (cached) · `CircuitBreaker` · `DailyBudget` (injected clock) |
| `jarvis/models/backends/claude.py` | `_serialize_prompt` · `_classify` · `claude_backend` · `ClaudeBackendError` |
| `jarvis/models/backends/state.py` | `get_backend(conn)` / `set_backend(conn, b)` → `system_state.llm_backend` |
| `jarvis/models/scheduler.py` (modify) | `chat(...)` gains `backend=` + the dispatch fork |
| `jarvis/config.py` (modify) | new settings |
| `jarvis/agents/conversation.py` (modify) | `_decide` pins `local`; answer path = "Claude composes" |
| `jarvis/routines/scheduler.py` (modify) | pass per-routine `action["backend"]` into the call |
| `jarvis/agents/postmortem.py` or its routine (modify) | pilot: `backend=claude` |
| `jarvis/cli/main.py` (modify) | `jarvis model [local|claude|status]` |
| `Dockerfile` / `Makefile` / `.env.example` (modify) | Node + claude CLI; `make claude-token`; docs |

Tests: one `tests/test_backends_*.py` per pure unit + `tests/integration/test_backends_state.py` +
`tests/test_scheduler_dispatch.py` + conversation test additions.

---

## Chunk 1: Pure units (no Ollama, no Claude, no DB)

### Task 1: Config

**Files:** Modify `jarvis/config.py`; `.env.example`.

- [ ] **Step 1 — failing test** (`tests/test_config.py`, append):
```python
def test_router_backend_defaults(monkeypatch) -> None:
    from jarvis.config import Settings
    s = Settings(_env_file=None)
    assert s.llm_default_backend == "local"          # safety net: never claude by default
    assert s.claude_breaker_cooldown_s == 900 and s.claude_daily_call_budget > 0
    monkeypatch.setenv("LLM_DEFAULT_BACKEND", "claude")
    assert Settings(_env_file=None).llm_default_backend == "claude"
```
- [ ] **Step 2 — run, expect fail:** `./.venv/bin/python -m pytest tests/test_config.py -k router_backend -q`
- [ ] **Step 3 — implement** (add to `Settings`, near the model-role block):
```python
    # Multi-backend router (off-GPU Claude via `claude -p`, owner subscription). Default local.
    llm_default_backend: Literal["local", "claude"] = "local"
    claude_call_timeout: int = 120          # seconds; hard ceiling on a claude -p call
    claude_availability_cache_ttl: int = 60
    claude_breaker_cooldown_s: int = 900    # rate-limit → force local for this long
    claude_daily_call_budget: int = 200     # soft per-UTC-day cap; exhausted → force local
    claude_model: str = ""                  # "" = CLI default; e.g. "claude-sonnet-4-…"
    # Secret: CLAUDE_CODE_OAUTH_TOKEN (via SecretsProvider/.env) — never a Settings field.
```
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit:** `git commit -am "config: multi-backend router settings (default local)"`

### Task 2: `resolve_backend` (pure)

**Files:** Create `jarvis/models/backends/__init__.py` (empty), `jarvis/models/backends/resolve.py`;
Test `tests/test_backends_resolve.py`.

- [ ] **Step 1 — failing test:**
```python
from jarvis.models.backends.resolve import resolve_backend as r

def test_precedence_and_hard_overrides() -> None:
    # precedence: explicit > routine > global
    assert r("claude", None, "local", has_schema=False, breaker_open=False, budget_exhausted=False) == "claude"
    assert r(None, "claude", "local", has_schema=False, breaker_open=False, budget_exhausted=False) == "claude"
    assert r(None, None, "claude", has_schema=False, breaker_open=False, budget_exhausted=False) == "claude"
    assert r(None, None, None, has_schema=False, breaker_open=False, budget_exhausted=False) == "local"
    # hard overrides → local
    assert r("claude", None, "claude", has_schema=False, breaker_open=True, budget_exhausted=False) == "local"
    assert r("claude", None, "claude", has_schema=False, breaker_open=False, budget_exhausted=True) == "local"
    # schema forces local UNLESS explicitly claude
    assert r(None, None, "claude", has_schema=True, breaker_open=False, budget_exhausted=False) == "local"
    assert r("claude", None, None, has_schema=True, breaker_open=False, budget_exhausted=False) == "claude"
```
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** `resolve.py`:
```python
"""Pure backend resolution — precedence + hard overrides. No I/O, fully unit-tested."""
from __future__ import annotations
from typing import Literal

Backend = Literal["local", "claude"]


def resolve_backend(
    explicit: Backend | None, routine: Backend | None, global_default: Backend | None,
    *, has_schema: bool, breaker_open: bool, budget_exhausted: bool,
) -> Backend:
    if breaker_open or budget_exhausted:
        return "local"                              # safety net always wins
    chosen: Backend = explicit or routine or global_default or "local"
    if chosen == "claude" and has_schema and explicit != "claude":
        return "local"                              # don't burn Claude on grammar-decode jobs
    return chosen
```
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit:** `git commit -am "router: pure resolve_backend (precedence + hard overrides)"`

### Task 3: `CircuitBreaker` + `DailyBudget` + `claude_available`

**Files:** Create `jarvis/models/backends/availability.py`; Test `tests/test_backends_availability.py`.

- [ ] **Step 1 — failing test:**
```python
from jarvis.models.backends.availability import CircuitBreaker, DailyBudget

def test_breaker_opens_then_closes() -> None:
    b = CircuitBreaker(cooldown_s=900)
    assert b.is_open(now=1000.0) is False
    b.record_rate_limit(now=1000.0)
    assert b.is_open(now=1100.0) is True       # within cooldown
    assert b.is_open(now=1901.0) is False      # cooldown elapsed → auto-close

def test_daily_budget_caps_and_rolls_over() -> None:
    bud = DailyBudget(limit=2)
    day = 1_700_000_000.0  # any epoch
    bud.record(now=day); bud.record(now=day)
    assert bud.exhausted(now=day) is True
    assert bud.exhausted(now=day + 86_400) is False   # new UTC day resets
```
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** (mirror `scheduler.SwapLimiter`'s injected-clock style):
```python
"""Claude availability + a rate-limit circuit breaker + a soft daily call budget (injected clock)."""
from __future__ import annotations
import datetime as _dt
import shutil
import time
from dataclasses import dataclass, field


class CircuitBreaker:
    def __init__(self, *, cooldown_s: int) -> None:
        self._cooldown = cooldown_s
        self._opened_at: float | None = None

    def record_rate_limit(self, *, now: float) -> None:
        self._opened_at = now

    def is_open(self, *, now: float) -> bool:
        return self._opened_at is not None and (now - self._opened_at) < self._cooldown


@dataclass
class DailyBudget:
    limit: int
    _day: str = ""
    _count: int = 0

    @staticmethod
    def _utc_day(now: float) -> str:
        return _dt.datetime.fromtimestamp(now, _dt.UTC).strftime("%Y-%m-%d")

    def record(self, *, now: float) -> None:
        d = self._utc_day(now)
        if d != self._day:
            self._day, self._count = d, 0
        self._count += 1

    def exhausted(self, *, now: float) -> bool:
        return self._utc_day(now) == self._day and self._count >= self.limit


_avail_cache: tuple[float, bool] = (0.0, False)


def claude_available() -> bool:
    """CLI on PATH AND the OAuth token present. Cached for claude_availability_cache_ttl."""
    global _avail_cache
    from jarvis.config import get_settings
    from jarvis.security.secrets import get_provider
    now = time.monotonic()
    ts, val = _avail_cache
    if now - ts < get_settings().claude_availability_cache_ttl:
        return val
    ok = shutil.which("claude") is not None and bool(get_provider().get("CLAUDE_CODE_OAUTH_TOKEN"))
    _avail_cache = (now, ok)
    return ok
```
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit:** `git commit -am "router: circuit breaker + daily budget + claude_available"`

### Task 4: Claude backend — serialize, classify, invoke

**Files:** Create `jarvis/models/backends/claude.py`; Test `tests/test_backends_claude.py`.

- [ ] **Step 1 — failing tests:**
```python
import json
import jarvis.models.backends.claude as cb

def test_serialize_strips_persona_tool_sections() -> None:
    msgs = [{"role": "system", "content": "You are Jarvis.\n\nWHAT YOU CAN DO:\n- restart"},
            {"role": "user", "content": "hi"}]
    p = cb._serialize_prompt(msgs, fmt=None)
    assert "You are Jarvis." in p and "WHAT YOU CAN DO" not in p and "User: hi" in p

def test_serialize_appends_schema_instruction() -> None:
    p = cb._serialize_prompt([{"role": "user", "content": "q"}], fmt={"type": "object"})
    assert "JSON" in p and "schema" in p.lower()

def test_classify_failures() -> None:
    assert cb._classify(124, "") == "timeout"
    assert cb._classify(1, "rate limit exceeded") == "resource_exhaustion"
    assert cb._classify(1, "Not logged in") == "permission_denied"

def test_run_normalizes_stdout(monkeypatch) -> None:
    monkeypatch.setattr(cb.subprocess, "run", lambda *a, **k: type("R", (), {
        "returncode": 0, "stdout": "Hello there.", "stderr": ""})())
    resp = cb.claude_backend("reasoning", [{"role": "user", "content": "hi"}], fmt=None, timeout=5)
    assert resp["message"]["content"] == "Hello there." and resp["backend_used"] == "claude"
```
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** `claude.py`:
```python
"""Claude backend — `claude -p` as a caged text-in/text-out endpoint, normalized to the Ollama dict.

Maximum cage (Hard Rule #1): no tools (--allowedTools ""), no MCP, no FS — run in an empty cwd so no
CLAUDE.md is read. Auth via CLAUDE_CODE_OAUTH_TOKEN (inherited from the container env)."""
from __future__ import annotations
import json
import subprocess
import tempfile
from typing import Any

_FAILURE = {"timeout": "timeout", "tool_unavailable": "tool_unavailable",
            "permission_denied": "permission_denied", "resource_exhaustion": "resource_exhaustion"}


class ClaudeBackendError(Exception):
    def __init__(self, failure_class: str, message: str) -> None:
        super().__init__(message)
        self.failure_class = failure_class


def _strip_tool_sections(system: str) -> str:
    # Persona's WHAT YOU CAN DO / WHAT YOU CAN OBSERVE list Jarvis's tools — noise to Claude.
    out = []
    for block in system.split("\n\n"):
        head = block.lstrip().upper()
        if head.startswith("WHAT YOU CAN DO") or head.startswith("WHAT YOU CAN OBSERVE"):
            continue
        out.append(block)
    return "\n\n".join(out)


def _serialize_prompt(messages: list[dict], *, fmt: dict | str | None) -> str:
    parts: list[str] = []
    for m in messages:
        role, content = m.get("role", "user"), str(m.get("content", ""))
        if role == "system":
            parts.append(_strip_tool_sections(content))
        else:
            parts.append(f"{role.capitalize()}: {content}")
    prompt = "\n\n".join(parts)
    if fmt is not None:
        prompt += ("\n\nRespond with ONLY a JSON object matching this schema (no prose, no "
                   f"markdown fences):\n{json.dumps(fmt)}")
    return prompt


def _classify(returncode: int, stderr: str) -> str:
    s = (stderr or "").lower()
    if returncode == 124:
        return "timeout"
    if "rate limit" in s or "usage limit" in s or "overloaded" in s:
        return "resource_exhaustion"
    if "not logged in" in s or "unauthorized" in s or "/login" in s:
        return "permission_denied"
    if "command not found" in s or "no such file" in s:
        return "tool_unavailable"
    return "unknown"


def claude_backend(role: str, messages: list[dict], *, fmt: dict | str | None, timeout: int) -> dict:
    from jarvis.config import get_settings
    s = get_settings()
    prompt = _serialize_prompt(messages, fmt=fmt)
    cmd = ["claude", "-p", prompt, "--allowedTools", "", "--output-format", "text"]
    if s.claude_model:
        cmd += ["--model", s.claude_model]
    try:
        with tempfile.TemporaryDirectory() as cwd:   # empty cwd → no CLAUDE.md pickup
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired as exc:
        raise ClaudeBackendError("timeout", str(exc)) from exc
    except FileNotFoundError as exc:
        raise ClaudeBackendError("tool_unavailable", str(exc)) from exc
    if proc.returncode != 0:
        raise ClaudeBackendError(_classify(proc.returncode, proc.stderr), proc.stderr or "claude failed")
    text = proc.stdout.strip()
    if "not logged in" in text.lower():
        raise ClaudeBackendError("permission_denied", text)
    return {"message": {"content": text}, "model": s.claude_model or "claude",
            "backend_used": "claude", "eval_count": 0, "prompt_eval_count": 0}
```
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit:** `git commit -am "router: claude backend (serialize/cage/classify/normalize)"`

## Chunk 2: DB state + the dispatch fork

### Task 5: Persisted global backend (`system_state.llm_backend`)

**Files:** Create `jarvis/models/backends/state.py`; Test `tests/integration/test_backends_state.py`
(`pytestmark = pytest.mark.integration`).

- [ ] **Step 1 — failing test:** start at `local` default, `set_backend(conn, "claude")` → `get_backend` returns `"claude"`; invalid value rejected.
- [ ] **Step 2 — run, expect fail/skip-if-no-DB.**
- [ ] **Step 3 — implement** mirroring `core/modes.py` (same `system_state` row helper; key `llm_backend`; `get_backend(conn)` falls back to `get_settings().llm_default_backend` when unset; `set_backend` validates `Literal["local","claude"]`).
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit.**

### Task 6: Dispatch fork in `scheduler.chat`

**Files:** Modify `jarvis/models/scheduler.py`; Test `tests/test_scheduler_dispatch.py`.

- [ ] **Step 1 — failing tests** (mock everything; no real Ollama/Claude/DB):
```python
import jarvis.models.scheduler as sch

def test_local_path_unchanged(monkeypatch):
    monkeypatch.setattr(sch, "_resolved_backend", lambda **k: "local")
    seen = {}
    monkeypatch.setattr(sch, "_run_local", lambda *a, **k: seen.setdefault("local", True) or {"message": {"content": "x"}})
    sch.chat("reasoning", [{"role": "user", "content": "hi"}])
    assert seen["local"]

def test_claude_schema_miss_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(sch, "_resolved_backend", lambda **k: "claude")
    monkeypatch.setattr(sch.claude_mod, "claude_backend", lambda *a, **k: {"message": {"content": "not json"}, "backend_used": "claude"})
    monkeypatch.setattr(sch, "_run_local", lambda *a, **k: {"message": {"content": "{}"}, "backend_used": "local"})
    events = []; monkeypatch.setattr(sch, "_emit", events.append)
    resp = sch.chat("reasoning", [{"role": "user", "content": "hi"}], format={"type": "object"})
    assert resp["backend_used"] == "local"
    assert any(e.type == "llm.fallback" for e in events)
```
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement:** refactor today's body of `chat` into `_run_local(...)` (byte-for-byte
  what it does now), add `backend: Backend | None = None` param, add `_resolved_backend(...)`
  helper (reads `state.get_backend` via a fresh `db.connect()`, the breaker/budget process-globals,
  `claude_available()`, and `has_schema = format is not None`), then:
  - `local` → `_run_local(...)`.
  - `claude` → `claude_mod.claude_backend(...)`; if `format` set, `json.loads`+`jsonschema.validate`
    → on `ValidationError`/`json` error **or** `ClaudeBackendError` → `_run_local(...)`, set
    `backend_used="local"`, `error=…`, `_emit(llm.fallback)`, debounced `notify.send`, and on a
    `resource_exhaustion` error `breaker.record_rate_limit(now)`; else `budget.record(now)`.
  - both paths `_emit(inference.completed)` with `backend` + duration.
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit.**

## Chunk 3: Wiring + deploy

### Task 7: Conversation — local routes / Claude composes

**Files:** Modify `jarvis/agents/conversation.py`; Test additions in `tests/test_conversation.py`.

- [ ] **Step 1 — failing tests:** `_decide` passes `backend="local"` to the scheduler (assert via
  monkeypatched `sched_chat`); when global backend is `claude` and `route=="answer"`, the answer is
  composed via a `sched_chat(..., backend="claude")` call (no `format`).
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement:** `_decide` → `sched_chat(..., backend="local")` (routing stays
  grammar-constrained). In `_reason`, after a successful `answer` route, if
  `state.get_backend(conn) == "claude"` and `claude_available()`, replace the answer text with a
  `_compose_answer(ctx, memory, utterance, facts)` that calls `sched_chat(..., backend="claude")`
  (no schema); otherwise keep today's path. Local backend → behavior identical to today (one call).
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit.**

### Task 8: Per-routine backend + postmortem pilot

**Files:** Modify `jarvis/routines/scheduler.py` (+ wherever the postmortem routine's `action` is
defined); Test in `tests/test_routines*.py`.

- [ ] **Step 1 — failing test:** a `Routine` whose `action` JSON has `{"backend": "claude"}` results
  in the inference call receiving `backend="claude"` (assert via monkeypatched scheduler).
- [ ] **Step 2 — fail. Step 3 — implement:** routine scheduler reads `action.get("backend")` and
  threads it as the per-task default into the agent call; set the postmortem routine's action
  `backend: claude`. **Step 4 — pass. Step 5 — commit.**

### Task 9: CLI `jarvis model`

**Files:** Modify `jarvis/cli/main.py`.

- [ ] **Step 1 — implement** a `model_app` Typer group: `jarvis model local|claude` →
  `set_backend`; `jarvis model status` → global default, `claude_available()`, breaker open?,
  today's budget used, last `llm.fallback` (from events). **Step 2 — `jarvis model status` runs.**
  **Step 3 — commit.**

### Task 10: Deploy — Dockerfile, Makefile, .env.example

**Files:** Modify `Dockerfile`, `Makefile`, `.env.example`. (No unit test; build-time.)

- [ ] **Step 1 — Dockerfile:** install Node + `npm install -g @anthropic-ai/claude-code` (pin a
  version), verify `claude --version` in the build.
- [ ] **Step 2 — Makefile:** `claude-token:` → `docker run --rm -it node:22 sh -c 'npm i -g
  @anthropic-ai/claude-code && claude setup-token'` (prints the token to paste into `.env`).
- [ ] **Step 3 — .env.example:** document `LLM_DEFAULT_BACKEND`, the `CLAUDE_*` knobs, and
  `CLAUDE_CODE_OAUTH_TOKEN` (secret; from `make claude-token`).
- [ ] **Step 4 — commit.** **Step 5 — `make deploy` on the box; `jarvis model status` shows
  `claude_available=true`; flip `jarvis model claude`; trigger a postmortem; confirm an
  `inference.completed` with `backend="claude"` and a clean fallback when the token is unset.**

---

## Acceptance (from the spec)
Unit: resolve precedence + overrides · breaker/budget clock · serialize (tool-strip + schema) ·
classify · normalize · schema-validate-then-fallback. Integration (auto-skip): local regression
(byte-for-byte) · claude path (`backend_used=="claude"`) · fallback (token unset → local, exactly
one notification) · chat-compose (routing `backend=local`, answer `backend=claude`) · cron routine
on claude falls back cleanly. Rollback: `jarvis model local` + unset the token. No migration.
