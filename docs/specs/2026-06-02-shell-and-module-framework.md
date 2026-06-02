# Shell + Module Framework + Session Login

> Date: 2026-06-02 · Personal-OS sub-project **#2** (after the router). The "one place" frame and
> the **repeatable backend+frontend template** every later module fills in. Build the template here
> once; every subsequent module is then fill-in-the-blanks. Inherits the foundation + master plan.

## Why this is foundation, not a feature

Tasks/Notes/Recipes/Email/etc. all want the *same* shape (CRUD table + gated tools + awareness event
+ search hook + route + panel + Cmd-K + theme). Defining that shape once — with a working "hello"
demo module that exercises it end-to-end — makes the rest cheap and symmetric. Also the natural,
non-disruptive moment to graduate auth from the localStorage bearer token to a real session login,
because the DB is about to hold the operator's whole life.

## Part A — Session login (replaces the bearer token)

- **Migration `0019_app_sessions`:** `app_sessions(token_hash, created_at, last_seen_at, expires_at,
  user_agent, revoked)`. Single operator; the passphrase hash lives in the box `.env`
  (`APP_PASSPHRASE_HASH`, argon2/bcrypt) via SecretsProvider — **never** in DB or git.
- **`jarvis/gateway/auth.py` (extend):** `POST /api/login` (passphrase → `hmac`/argon2 verify →
  mint opaque session token, store **hash** only, set `HttpOnly`, `SameSite=Strict`, `Secure`
  cookie) · `POST /api/logout` (revoke) · session middleware (cookie → hash lookup → not-revoked +
  not-expired; sliding `last_seen_at`). Keep `hmac.compare_digest` everywhere. The existing bearer
  token stays accepted for one release as a fallback, then is removed.
- **Frontend:** a login screen; on 401 the app routes to it; `web/src/api.ts` switches from the
  `Authorization` header to credentialed cookies (`fetch(..., {credentials:"include"})`,
  `wsUrl()` unchanged but cookie carried). Logout in the shell menu.
- **Gating note:** login/logout are gateway endpoints, not Jarvis tools — no Intent path. Still
  Tailscale-only / never publicly exposed (DECISIONS unchanged).

## Part B — The shell (frontend frame)

- **`web/src/shell/`**: a persistent left **nav** (or bottom bar on mobile, reuse safe-area work) +
  a content area + a top bar (presence orb mini, global Cmd-K, theme menu, logout). The existing
  surfaces (chat console, torrents, etc.) become **routes inside the shell**, not the whole app.
- **Router:** client-side routes `/`, `/chat`, `/tasks`, `/notes`, … one per module. A module
  **registers** `{ id, title, icon, route, panel, cmdkProvider, themeTokens? }` in a central
  `modules/registry.ts`; the shell renders nav + routes from the registry. **Adding a module = one
  registry entry + a panel component** — this is the frontend half of the template.
- **Cmd-K / global search:** a palette that fans out to each module's `cmdkProvider` (and the
  existing search). Providers return `{ title, subtitle, entity_ref, action }`. Backed by the
  shared search hook (Part D).
- **Theming:** keep the existing custom-theme tokens (CSS variables already in the console). Ship a
  small set of presets + the existing custom theme; persisted per-operator (localStorage now, DB
  `user_facts` later). Every module consumes theme tokens — no hard-coded colors.

## Part C — The backend module template (`jarvis/<module>/`)

Codify the pattern as a **documented convention + tiny shared helpers**, not a heavy framework:

- **Table:** `<module>(id, …fields…, schema_version, entity_ref, created_at, updated_at)`; stable
  `entity_ref = "<module>:<id>"`. New `jarvis/ids.py` prefix per module.
- **Pydantic model** at the boundary (`schema_version`, validation, `field_validator`s) — mirror
  `reminders.py`.
- **Repository** (`repository.py`): CRUD over psycopg, returns models.
- **Gated tools** (`tools.py` → register in `tools/registry.py`): `<module>.create/update/delete/…`
  with a `Tool` contract (`version`, `permissions`, `side_effects`, `idempotent`, `rollback`).
  **Grading helper** (`tools/grading.py`, new): given `risk`/`reversible`/`side_effects`, decide
  auto-run vs gated — reversible + low-risk + on-box → **auto-run**; else **gated**. The mode ladder
  (`observe`/…) still overrides. This is Evolution #2 made concrete and is **shared by all modules**.
- **Awareness event** (`<entity>.<verb>` past-tense, `info`): emitted on significant change; a
  *notice* for the timeline + conversation context, **not** the source of truth. Carries
  `entity_ref` + `correlation_id`.
- **Search hook** (Part D): index text fields into the existing memory/pgvector retrieval.
- **Context accessor:** a `recent(...)`/`search(...)` the conversation agent's context assembly can
  call so Jarvis is aware of the module's content.

## Part D — Shared search hook

A thin `jarvis/<module>` → `memory` indexing helper: on create/update, embed the module's text
(reuse `nomic-embed-text` + `MemoryStore`) tagged with `entity_ref` + a `source=<module>` facet;
deletes purge. Cmd-K and the conversation agent both query it. **No new vector store** — reuse
pgvector + the existing retrieval machinery (foundation rule).

## Part E — The "hello" demo module (proves the template end-to-end)

A throwaway **`scratch` module**: one table, one `scratch.create`/`delete` auto-run tool, an
awareness event, a search hook, a nav entry + panel + Cmd-K provider. It exists to **exercise and
document the template**, is covered by tests, and is deleted (or kept as the living example) once
two real modules (Tasks, Notes) exist. Its real value: the diff that adds it is the **checklist**
for every future module.

## Events / data

`0019_app_sessions`. No other migration (the template is convention; modules bring their own tables).
New events are per-module (`scratch.created` for the demo). `inference.completed` unaffected.

## Testing → acceptance

- **Unit:** session token mint/verify/revoke/expiry (injected clock); auth middleware (valid cookie /
  missing / revoked / expired); the grading helper (auto-run vs gated truth table incl. mode-ladder
  override); the demo module's tool + awareness event + search indexing (mocked embedder).
- **Frontend (vitest):** login flow (401 → login → cookie → app); module registry renders nav+routes
  from entries; Cmd-K fans out to providers; theme switch updates tokens; existing surfaces still
  render inside the shell.
- **Integration (auto-skip):** end-to-end login against the gateway; the `scratch` module round-trips
  (create via tool → row + event + searchable → appears in Cmd-K → delete purges).
- **Gate:** login works; chat/torrents render inside the shell; the demo module proves backend+
  frontend template; theme switch works; full suite + lint green; **bearer-token fallback still
  works this release** (no lockout).

## Plan (TDD task list — re-validate against `main` before building)

1. **Migration `0019_app_sessions`** + `AppSession` model + repository. Test: schema + CRUD.
2. **`auth.py`**: passphrase verify (env hash), session mint/verify/revoke/expiry helpers (injected
   clock), middleware. Tests first. Keep bearer fallback.
3. **`/api/login` + `/api/logout`** endpoints + cookie wiring. Integration test.
4. **Frontend api/auth switch** to credentialed cookies + login screen + 401 redirect + logout. vitest.
5. **`tools/grading.py`** shared auto-run/gated decision + truth-table tests (this unblocks every module).
6. **Shell frame** (`web/src/shell/`) + client router + move existing surfaces into routes. vitest.
7. **`modules/registry.ts`** + nav/route rendering from entries. vitest.
8. **Cmd-K palette** + provider fan-out. vitest.
9. **Theme menu** + presets + per-operator persistence; audit modules consume tokens. vitest.
10. **Shared search hook** helper (embed-on-write, purge-on-delete, `source` facet). Unit (mock embedder).
11. **`scratch` demo module** exercising the full backend+frontend template + the registry entry.
    Integration round-trip. This diff becomes the per-module checklist.
12. **Docs:** nested `jarvis/<module>/CLAUDE.md`-style note? No — instead add a `docs/MODULE_TEMPLATE.md`
    distilled from the `scratch` diff. Update MAP.md (shell, registry, grading) + STATUS.

## Non-goals

No SSO / OAuth login (single operator, passphrase). No multi-user. No offline-first rewrite (PWA
shell stays as-is). No public exposure. The template is a convention + small helpers, **not** a
heavyweight plugin framework (the `plugins/` SDK already covers external HTTP tools).
