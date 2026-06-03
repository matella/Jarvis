# Module Template — how to add a personal-OS module

> The repeatable backend pattern, distilled from the built modules (`tasks`, `notes`, `documents`,
> `recipes`, `mail`, `calendar`, `research`, `cookbook`, `code`). Adding a module = filling this in.
> Frontend (route + panel + Cmd-K + theme) is a separate, held layer — see the shell spec.

## Backend checklist (per user-document module)

1. **Migration** `migrations/versions/00NN_<module>.py` — a CRUD table: `id` (prefixed, see below),
   the module's fields, `schema_version`, `created_at`, `updated_at`, plus a soft-delete column
   (`status`/`archived`) — kept for audit, never hard-deleted. The table **owns the truth** (the
   event log does not). Reconfirm the next free revision number; the `revises` chain is linear.
2. **`jarvis/ids.py`** — add a prefix constant; `entity_ref` is `"<module>:<id>"`.
3. **`jarvis/<module>/models.py`** — a Pydantic model at the boundary: validators (trim/normalize),
   `schema_version`, an `entity_ref` property, a `search_text()` if indexed. Re-validate on update by
   rebuilding the model from `model_dump()`.
4. **`jarvis/<module>/repository.py`** — the **single write path**. CRUD that:
   - emits a light **awareness event** via `jarvis.modules.awareness.emit_awareness`
     (`<entity>.<verb>` past-tense, best-effort — never fails the write; it's a notice, not truth);
   - keeps the **search index** in sync via `jarvis.modules.search` (`index_entity` /
     `reindex_entity` / `purge_entity`), gated behind an `index: bool = True` param so DB-only
     integration tests can pass `index=False` (no embedder needed);
   - exposes **read accessors** the conversation agent + daily brief use (`recent`, `due_before`,
     `agenda`, …). Both the operator (UI/REST) and Jarvis (Intent→tool) write through here.
5. **`jarvis/<module>/tools.py`** — capability tools registered via `jarvis.tools.registry.register`:
   - reversible / on-box / no-side-effect CRUD → `side_effects=False` ⇒ the agent builds an **auto-run**
     intent (executes unattended in `semi_autonomous`). See `jarvis.tools.grading` for the policy;
   - external / irreversible work (web fetch, send, apply) → `side_effects=True` ⇒ **gated**;
   - `run(target, *, timeout_s)` validates `target`, opens `db.connect()`, calls the repository,
     raises `ValueError` on bad input (→ `validation_failure`). The return value is **discarded** by
     the execute path — so anything the operator must SEE (a proposal/diff) is a gateway/UI flow, not
     a tool (e.g. `documents.ai.propose_edit`).
6. **Register** the module's tools in `jarvis/modules/builtin_tools.py` (imported by the gateway +
   the conversation agent, so the registry is populated wherever the agent runs).
7. **Multi-step work** (research, import, co-write) = a **deterministic harness over one-shot
   inferences** (Hard Rule #2): plan/fan-out/synthesize bounded by caps; inject `chat_fn`/`fetch_fn`
   so it unit-tests without Ollama/network; failures degrade (partial), never loop.
8. **Per-action model choice** — heavy/prose inferences resolve their backend via
   `jarvis.cookbook.backend_for_action("<module>.<action>")` (best-effort; default `None` lets the
   router decide). The router's resolution + hard overrides are unchanged.
9. **Tests:** model validation + tool target-parsing/gating as **unit** (no DB/LLM, mock the conn +
   inject `chat_fn`); the repository round-trip + search/awareness as **integration**
   (`pytestmark = pytest.mark.integration`, uses the `db_conn` fixture, auto-skips without a DB).
10. **Lint+test gate:** `ruff check jarvis tests` clean and `pytest -m "not integration"` green
    **before** committing. Keep lines ≤ 100 cols. Update MAP.md + STATUS.

## Operational (event-sourced) modules

Memories/Routines UI surface **existing** operational tables — no new table, no new tools, no LLM.
Their backend is just gateway REST reads + actions that delegate to existing governance/scheduler
code. (Held with the frontend.)

## Cross-module linking (free — no graph DB)

Set `source_entity_ref` on a created row to record provenance ("from `mail:<id>`"); the causal chain
rides `correlation_id`. "email → task → calendar → note → doc" are reachable by reference alone.

## Frontend (held — build with the shell)

Route + nav entry + panel + Cmd-K provider + theme tokens, registered in `web/src/modules/registry`.
Mechanical once the shell exists; needs a browser to verify UX, so it's deferred to a review session.
