# M3 — Add the Model (design spec)

> Date: 2026-05-29 · Milestone: **M3** (see `docs/PLAN.md`). First milestone with an LLM.
> The model only *compresses/summarizes* deterministically-assembled context — it never
> touches infrastructure and never chooses what to retrieve.

## Acceptance test (from PLAN.md)
`jarvis summarize --since 12h` → prose grounded in real `events`
(e.g. "3 containers restarted overnight from OOM pressure…"), with `inference.completed`
events showing per-call timing.

## Decisions
- **Full multi-model routing**, config-driven model **roles** → Ollama tags:
  `reasoning=qwen3:8b` · `coder=qwen2.5-coder:7b` · `embedding=nomic-embed-text`
  (`.env` overrides; `llama3.2:latest` is the interim reasoning placeholder while qwen3 pulls).
  "Qwen 3.5 9B" from CLAUDE.md has no literal Ollama tag — `qwen3:8b` is the 8 GB-fit stand-in.
- **One LLM resident at a time**, enforced by `keep_alive` + explicit unload of the prior
  model; **global inference semaphore (concurrency = 1)** serializes all inference.
- **Context assembly is pure deterministic code**: recency + entity match + vector relevance,
  token-budgeted ≤ 8K. The LLM is handed the result; it does not retrieve.
- **Reach Ollama via the SSH tunnel** (`127.0.0.1:11434`), consistent with PG/Redis (off-LAN).
- **Model/inference events flow through the Redis spine** (M2), so they appear in
  `events tail`/`trace`.
- **Summarizer output structured**: `SummaryResult {window, event_count, summary, notable[]}`
  — `summary` is LLM prose; `notable[]` is the deterministic warning/critical list (robust
  even with a weak placeholder model).

## Components (MAP.md seams)
- **`models/client.py`** — Ollama client (official `ollama` pkg, host from `ollama_url`):
  `chat`, `embed`, `ps`, `unload`.
- **`models/router.py`** — role→tag policy + module-level `Semaphore(1)`. `chat(role, messages)`
  / `embed(text)`: acquire semaphore → ensure target model resident (unload others) → call →
  emit `model.loaded` (by diffing `ps()`) + `inference.completed` Events (model, role,
  `duration_ms`, prompt/eval tokens, `context_ref` hash, `correlation_id`) to the spine.
- **`core/assembly.py`** — `assemble_context(conn, *, since, entity=None, query=None,
  budget_tokens=8192)` → `AssembledContext {events[], memories[], prompt, context_ref}`.
  Recency (window) + entity filter + vector relevance (`embed(query)` → `MemoryStore.search`),
  trimmed to budget (≈4 chars/token heuristic), deterministic ordering. `context_ref=ctx_<sha>`
  over the rendered prompt + model params.
- **`agents/summarizer.py`** — `SummaryResult` model + one-shot `summarize(since)`:
  new `correlation_id` → fetch window events → `assemble_context` → **one** `router.chat`
  (reasoning) → build `SummaryResult` (`notable[]` deterministic) → `embed` summary +
  `MemoryStore.add` (episodic, kind=`summary`). Two inferences total (reasoning + embed),
  which exercises a real GPU swap.
- **`cli`** — `jarvis summarize --since 12h` (Rich), `jarvis models` (roles + `ollama ps`).
- **config** — `ollama_host/port/url`, `model_reasoning/coder/embedding`, `keep_alive`,
  `inference_context`. **Makefile** tunnel adds `11434`; **healthcheck.py** adds an Ollama ping.

## Event types added
`model.loaded` (info, entity=`model:<tag>`) · `model.unloaded` (info) ·
`inference.completed` (info; payload: model, role, duration_ms, total/load ns, prompt_eval_count,
eval_count, context_ref).

## Testing → acceptance
- **Unit** (no Ollama): role→tag resolution; token-budget trimming + deterministic ordering in
  `assemble_context` (fed synthetic events); `SummaryResult.notable[]` derivation; event-builder
  payload shape. Ollama client mocked.
- **Integration** (Ollama+DB via tunnel, `@pytest.mark.integration`, auto-skip): `router.embed`
  returns a 768-vector and round-trips through `MemoryStore`; `router.chat` returns text and
  emits an `inference.completed` Event; a swap (reasoning→embedding) produces `model.loaded`.
  Skips cleanly if the model tags aren't pulled.
- **Live acceptance**: ingest+consume+restart a probe to seed events, then
  `jarvis summarize --since 1h`; confirm grounded prose + `inference.completed` in `events tail`.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
