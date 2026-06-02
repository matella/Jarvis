# Multi-Backend LLM Router — `local` (Ollama) + `claude` (`claude -p`)

> Date: 2026-06-02 · First sub-project of the personal-OS arc
> (see `2026-06-02-personal-os-foundation.md`). Adds an opt-in second reasoning backend
> (Claude via `claude -p`, owner subscription — no API key, no metered billing) behind the
> existing single switch point, defaulting to `local` so Jarvis never goes dark. It is both a
> quality upgrade *and* the off-GPU relief valve the multi-module future needs.

This finalizes the upstream router spec with the brainstorming refinements (below). Where this doc
and the original differ, **this doc wins**.

## Refinements applied (from review)

1. **Step 0 spike — DONE (verified on the box 2026-06-02, CLI v2.1.160).** Findings:
   - **Auth = `CLAUDE_CODE_OAUTH_TOKEN` env var** (long-lived subscription token from
     `claude setup-token`; NOT metered API key). `setup-token` does *not* persist a credential
     file — so **no `claude-config` volume and no interactive in-container login**. The token is a
     **secret in `.env`**, passed to the containers by the existing `env_file` wiring. Persistence
     is solved by design (env var survives restart/rebuild); no write-race on a shared file.
   - **Maximum cage = `claude -p "<prompt>" --allowedTools "" --output-format text`** run in an
     **empty cwd** (no `CLAUDE.md` pickup) and **no `--mcp-config`** → pure text-in/text-out, no
     tools, no MCP, no FS. (`json` output available for token-usage → best-effort `eval_count`.)
   - Caged completion returns real text; unauthed correctly errors "Not logged in".
   - **Token rotation:** re-run `setup-token` when it expires → update `.env` → redeploy.
2. **Chat shape = "local routes, Claude composes."** The conversation agent keeps its
   **grammar-constrained routing inference on `local`** (the `_Decision` schema call — `_decide`
   pins `backend=local`); only the **free-text answer** is generated on the resolved backend.
   Claude is spent where prose quality shows, never on the schema-constrained decode (avoids the
   double-latency Claude→miss→local path).
3. **Aim Claude at free-text, keep structured decode on local.** Any `scheduler.chat` call that
   passes a `format` schema resolves to `local` unless the caller *explicitly* sets `backend=claude`
   (e.g. a deliberate schema-on-Claude task); schema-on-Claude still injects+validates+falls back.
4. **Soft daily budget** alongside the breaker: a per-day Claude call cap (modeled on
   `BudgetLedger`) so a runaway routine can't burn the whole subscription before the breaker trips.
5. **Pin replays to `local`** — decided, not deferred (`eval/harness::replay_intent` is a
   regression check; non-deterministic, subscription-burning Claude defeats it).
6. **Thin v1**: ONE Claude model (no `model_hint→model` map), CLI-only (`jarvis model`), global
   toggle + the postmortem task + the chat-compose path. Everything else expands after a day.
7. **Strip tool/persona-capability content** from the prompt sent to Claude (it has none of
   Jarvis's tools; the "WHAT YOU CAN DO/OBSERVE" sections are noise to it).
8. **Note** the gateway↔daemon credential-refresh write race on the shared `claude-config` volume
   (low risk; tolerate/serialize if observed).

## Decisions carried forward (unchanged from the upstream spec)

- **Dispatch fork in `scheduler.chat` (Approach A)** — above the GPU semaphore. `local` →
  today's `get_scheduler().run()` path byte-for-byte; `claude` → call the Claude backend directly,
  bypassing the scheduler (off-GPU: must not take the resident slot nor count against the swap
  limiter). Zero call-site churn.
- **Keep the Ollama dict response shape.** Claude adapts to it: `{"message": {"content": …},
  "model": "claude-…", "eval_count": …, "backend_used": "claude"}`. Downstream
  `resp["message"]["content"]` unchanged.
- **Backend resolution precedence:** explicit per-call `backend` > per-routine `backend` > global
  persisted default (`system_state.llm_backend`) > `LLM_DEFAULT_BACKEND` env (default `local`).
  **Hard overrides:** breaker open → `local`; a `format` schema present and no explicit
  `backend=claude` → `local`; daily budget exhausted → `local`.
- **Maximum cage (Hard Rule #1):** `claude -p` as a pure text-in/text-out completion — all tools,
  MCP, filesystem disabled. Exact flags verified on the box.
- **Rate-limit ⇒ circuit breaker** forcing `local` for `claude_breaker_cooldown_s` (~900s), one
  debounced notification, auto-close; injected clock (mirrors `SwapLimiter`).
- **Global interactive default persisted in DB** (`system_state`, like `JARVIS_MODE`) — survives
  `make deploy`. **Per-task `backend`** rides the existing `Routine.action` JSON (no migration).

## Components (MAP.md seams)

- **`jarvis/models/backends/resolve.py`** — pure `resolve_backend(explicit, routine_backend,
  global_default, *, has_schema, breaker_open, budget_exhausted) -> Literal["local","claude"]`.
  Precedence + all three hard overrides. Fully unit-tested.
- **`jarvis/models/backends/claude.py`** — `claude_backend(role, messages, *, format, timeout)`:
  `_serialize_prompt` (system+messages → one role-prefixed prompt, persona tool-sections stripped);
  if `format`, append a "respond with JSON matching this schema" instruction;
  `subprocess.run(["claude","-p", …caged flags…], timeout=…, capture_output=True)`; parse stdout →
  Ollama dict shape (`backend_used="claude"`); classify failures (`timeout` / `tool_unavailable`
  (CLI missing) / `permission_denied` (unauthed) / `resource_exhaustion` (rate-limit) / `unknown`)
  → typed `ClaudeBackendError(failure_class, …)`.
- **`jarvis/models/backends/availability.py`** — `claude_available()` (`command -v claude` AND
  `CLAUDE_CODE_OAUTH_TOKEN` present via SecretsProvider; cached `claude_availability_cache_ttl`=60s);
  `CircuitBreaker`
  (`open`/`is_open`/`record_rate_limit`, injected clock, process-global); `DailyBudget`
  (per-UTC-day call counter, injected clock).
- **`jarvis/models/backends/state.py`** — read/write `system_state.llm_backend`, reusing the
  `core/modes.py` row helper.
- **`jarvis/models/scheduler.py`** — `chat(...)` dispatch fork: resolve backend → `local` (existing
  path, untouched) | `claude` (`claude_backend` directly; if `format`, validate, on miss/
  `ClaudeBackendError` fall back to `local`, set `backend_used="local"`+`error`, emit `llm.fallback`,
  notify (debounced), on rate-limit `breaker.record_rate_limit(now)`); emit `inference.completed`
  (model, `backend`, duration) for both paths; `DailyBudget` incremented on claude success.
- **`jarvis/agents/conversation.py`** — `_decide` pins `backend="local"` (schema routing stays on
  local); the answer/compose path (`_plain_answer` / the answer branch) passes no schema and uses
  the **resolved** backend → Claude composes the free-text reply when the global default is `claude`.
- **`jarvis/routines/models.py`** — `action` JSON carries optional `backend`; the routine scheduler
  passes it as the per-task default. Pilot: the `postmortem` task sets `backend: claude`.
- **`jarvis/cli/main.py`** — `jarvis model [local|claude|status]` (status: global default,
  `claude_available()`, breaker state, today's budget used, last fallback).
- **config / `.env.example`** — `llm_default_backend="local"`, `claude_call_timeout`,
  `claude_availability_cache_ttl=60`, `claude_breaker_cooldown_s=900`, `claude_daily_call_budget`,
  `claude_model`. **Secret:** `CLAUDE_CODE_OAUTH_TOKEN` (via SecretsProvider/`.env`, never logged).
- **Dockerfile** — add Node + `@anthropic-ai/claude-code` (the CLI binary).
- **docker-compose.yml** — **no volume needed.** `CLAUDE_CODE_OAUTH_TOKEN` reaches both gateway and
  daemon via the existing `env_file: .env`.
- **Makefile** — `make claude-token` → run `claude setup-token` in a throwaway container to mint the
  long-lived token; operator pastes it into the box `.env` as `CLAUDE_CODE_OAUTH_TOKEN`.

## Events / data

`llm.fallback` (warning; `intended_backend`, `failure_class`, `reason`, `correlation_id`) ·
`inference.completed` gains `backend` (`local`|`claude`). Response dict (both backends):
`message.content` (str), `model`, `backend_used`, `eval_count`/`prompt_eval_count` (claude
best-effort/0), optional `error` (set on fallback). No migration (routine field rides JSON; global
default rides `system_state`).

## Replay

`replay_intent` pins `backend=local` (regression check; deterministic; zero subscription burn).

## Testing → acceptance

- **Unit (no Claude/Ollama):** `resolve_backend` precedence + all hard overrides (breaker /
  has_schema / budget force `local`); `_serialize_prompt` (incl. persona tool-section stripping);
  response normalization (mocked stdout → dict); schema-validate-then-fallback (invalid JSON →
  local); `CircuitBreaker` + `DailyBudget` with injected clock; failure-class classification from
  stderr/exit-code fixtures.
- **Integration (`@pytest.mark.integration`, auto-skip):** local regression guard (byte-for-byte);
  claude path (authed → real completion, `backend_used=="claude"`, `inference.completed` carries
  `backend="claude"`); fallback (unset `CLAUDE_CODE_OAUTH_TOKEN` or rename `claude` on PATH →
  succeeds via local, exactly **one** notification); persistence (token in `.env` → survives
  rebuild; trivial since it's an env var); cron (`backend: claude` routine
  runs + falls back cleanly when down); **chat-compose** (toggle on → routing event shows
  `backend=local`, the answer's `inference.completed` shows `backend=claude`).

## Rollout (small, reversible)

0. **Spike — DONE** (auth = `CLAUDE_CODE_OAUTH_TOKEN` env var; caged `-p --allowedTools ""`; verified
   on the box). Gate passed.
1. Branch.
2. Land the dispatch fork + both backends + breaker + budget, default `local`. Behavior identical
   to today (all Ollama) — zero-risk merge.
3. Pilot: `jarvis model claude` (chat → local routes / Claude composes) **and** `postmortem` task
   `backend: claude`. Observe a day: latency, fallback events, auth stability, breaker/budget.
4. Expand per-task `backend: claude` to planner + routine briefings; high-frequency/cheap jobs
   (embeddings, reactor, anomaly, triage, routing) stay on `local`.
5. Rollback = flip defaults to `local` / merge out. No migration.

## Non-goals

No reverse-engineered API proxy. No multi-user / rate-limit *enforcement* layer. No public
exposure. No browser-login automation. No `model_hint→model` map in v1. No local→claude promotion
of high-frequency cheap work.
