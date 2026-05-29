# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**M3 — Add the model** · *DONE (acceptance passed live on remote GPU)*

## Done
- M0 (infra) + M1 (contracts) + M2 (event spine) DONE — see git history.
- M3 design in `docs/superpowers/specs/2026-05-29-m3-add-the-model-design.md`
  (full multi-model routing · config-driven roles · structured summarizer).
- Models pulled on remote: `qwen3:8b` (reasoning), `qwen2.5-coder:7b` (coder),
  `nomic-embed-text` (embedding), + `llama3.2` placeholder. Tags are config (`MODEL_*`).
- M3 built: `models/client.py` (Ollama wrapper); `models/router.py` (role→tag policy,
  global inference semaphore=1, one-resident enforcement, emits model.loaded/unloaded/
  inference.completed events to the spine); `core/assembly.py` (deterministic recency +
  entity + vector-relevance, ≤8K, context_ref hash); `agents/summarizer.py` (one-shot
  → SummaryResult{window,event_count,summary,notable[]}, stores summary in `memory`);
  CLI `summarize` + `models`; Ollama in healthcheck; tunnel adds 11434.
- **M3 acceptance PASSED** live: `jarvis summarize --since 1h` produced grounded prose +
  deterministic notable[]; one run drove 3 inferences with real GPU swaps, all visible as
  `inference.completed` (qwen3:8b reasoning ~9.6s, nomic embed ~1-6s) + model.loaded/unloaded
  events, reasoning call carrying `context_ref`. `pytest` 34/34, `ruff` clean.

## In progress
- *(nothing — ready to start M4)*

## Next step — do this first
Begin **M4 — intent loop (read-only first)**: infrastructure agent proposes Intents
(investigate/recommend) validated vs schema + capabilities, logged with `context_ref`;
the **tool contract** (version/permissions/side_effects/idempotent/max_retries/
timeout_seconds/rollback) + capability-scoped executors; global `mode` (default `observe`)
+ approval gate; CLI `inspect intent`/`explain`/`replay`. **Acceptance:** agent proposes a
`restart_container` intent with confidence/risk/reversible; approval gate works under
`observe`; execution recorded as a separate `executions` row sharing the correlation_id;
`jarvis explain` surfaces the stored context. See `docs/PLAN.md`.

## Open questions / blockers
- *(none)*

## Notes for next session
- Integration tests need the SSH tunnel up (now incl. 11434) + `alembic upgrade head`.
- Run live: `jarvis ingest` + `jarvis consume`; then `jarvis summarize --since 1h`.
- Reasoning defaults to `qwen3:8b`; set `MODEL_REASONING=llama3.2:latest` in `.env` for fast/cheap.
- `snapshots` table still has no model/writer (compaction comes later).

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.
