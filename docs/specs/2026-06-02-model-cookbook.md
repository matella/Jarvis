# Model Cookbook + Per-Action Model Picker

> Date: 2026-06-02 · Personal-OS module (step 8). A **router follow-up + UI** — no new data class,
> no LLM step. Lets the operator see and set **which backend (+ later, which model/params) each
> action or routine uses**, via persisted presets ("recipes" for the model). Honored by the router's
> existing resolution precedence. Inherits the foundation; closes the router arc.

## What it adds (and what it reuses)

The router already resolves `explicit > per-routine > global > env-default`, with hard overrides
(breaker/budget/schema). This module makes the **per-action/per-routine** layer **operator-editable
and persistent**, and adds **named presets** so common configs are one click. It does **not** change
the resolution algorithm — it feeds it stored values.

## Shape

- **Migration `0027_model_prefs`:** `model_prefs(id, scope, scope_key, backend, model, params_json,
  preset_name, schema_version, created_at, updated_at)`. `scope ∈ {action, routine, global}`;
  `scope_key` = the action name (e.g. `postmortem`, `document.ai_edit`, `research.synthesize`) or
  routine id; `backend ∈ {local, claude}`; `model`/`params_json` reserved for the future
  `model_hint→model` map (v1 leaves `model` empty → the backend's single model). `ids.MODELPREF`.
- **Presets ("cookbook"):** named rows with `scope=global`/templates, e.g. *"Quality"*
  (claude for compose/research/postmortem, local for triage/routing), *"Frugal"* (all local),
  *"Balanced"*. Applying a preset writes the per-action rows.
- **Resolution wiring:** `backends/state.py` / `resolve.py` gain a `prefs` lookup: when
  `scheduler.chat` resolves a backend, it consults `model_prefs` for the call's action key
  (passed as today's per-routine `backend` is, but now also per-action). Precedence unchanged:
  explicit per-call still wins; prefs fill the per-action/per-routine slot. **Hard overrides
  (breaker/budget/schema→local) still win over any pref** (safety net intact).
- **No new tools / no LLM.** Pure config CRUD over `model_prefs` + a gateway read/write.
- **Events:** `model.pref_changed` (`info`; scope, key, backend) for the audit/timeline.

## Cross-module

Every module that calls `scheduler.chat` with an action key automatically becomes configurable here:
`document.ai_edit`, `research.synthesize`, `mail.draft`, `postmortem`, conversation `compose`, etc.
This is the single dial behind the whole arc's "use the strong model here, the cheap one there."

## Frontend

Route `/models` + nav + panel: a table of actions/routines × backend (dropdown), preset chooser
(apply Quality/Frugal/Balanced/custom), live router status (reuse `jarvis model status` data:
claude availability, breaker, today's budget, 24h usage-by-backend from `inference.completed`).
Read-only mirror of routine backends (the Routines UI links here). Cmd-K: "set <action> to claude".
Theme tokens.

## Testing → acceptance

- **Unit:** `model_prefs` CRUD + validation; resolution consults prefs at the right precedence slot;
  **hard overrides still beat prefs** (breaker/budget/schema→local regardless of a `claude` pref);
  applying a preset writes the expected rows; `model.pref_changed` emitted.
- **Integration (auto-skip):** set `document.ai_edit=claude` → that call resolves claude (then falls
  back if down); set global Frugal → everything local; routine backend reflected read-only in
  Routines UI.
- **Frontend (vitest):** table renders + edits; preset apply; status panel from fixtures; Cmd-K.
- **Gate:** per-action/per-routine backend editable + persisted + honored; presets work; safety
  overrides intact; suite + lint green.

## Plan (TDD)

1. `0027_model_prefs` migration + `ModelPref` model + repository. Tests.
2. Resolution wiring: `resolve.py`/`state.py` consult prefs at the per-action/per-routine slot;
   hard-override-beats-pref tests first. (Touches the router — re-run its suite.)
3. Presets (Quality/Frugal/Balanced) apply→rows + `model.pref_changed`. Unit.
4. Gateway read/write for prefs + status (reuse `jarvis model status` data). Tests.
5. Frontend: table + preset chooser + status panel + Cmd-K. vitest.
6. CLI: extend `jarvis model` with `pref set <action> <backend>` / `preset <name>`. Tests.
7. MAP.md + STATUS. Close the router arc note.

## Non-goals

No `model_hint→model` multi-model map *behavior* in v1 (schema reserves `model`/`params`; the
backends still each expose one model). No autoscaling/learned routing. No per-user prefs (single
operator). Resolution algorithm unchanged — this only supplies stored values.
