# Personal-OS Arc — Master Build Plan

> Date: 2026-06-02 · The sequencing + dependency spine for the whole "personal life OS" arc.
> Inherits `2026-06-02-personal-os-foundation.md` (two data classes, graduated gate, deterministic
> harnesses, module framework). Each module has its own self-contained spec+plan file (same date
> prefix). This doc is the order, the shared decisions, the migration ledger, and the go/no-go gates.
> **Read this first; then the per-module file when you build that module.**

## Decisions locked for the whole arc (answered 2026-06-02)

- **App auth:** real **single-user session login** lands in the **shell foundation** (hashed
  passphrase, server-side session, cookie, logout). Replaces the localStorage bearer token.
  Tailscale-only, never public. (`code-opencode`, `email`, `calendar` assume it exists.)
- **Email v1:** **generic IMAP/SMTP** (app-password), one provider-agnostic path. Read+triage+search
  ungated; **compose/send gated**. No OAuth.
- **Documents:** **Markdown-first** storage (one text column; render rich, edit markdown/hybrid).
  Research output and co-writing land here as markdown.
- **Calendar v1:** **Google OAuth read-mirror** (real Google events pulled read-only) **+** a local
  editable calendar table (Jarvis/you author events). No write-back to Google in v1. Keep the
  existing ICS read connector for other external calendars.
- **"Open code" = OpenCode** (opencode.ai) → a **Code module**: OpenCode runs **headless in an
  isolated git worktree** as a gated coding *harness* (its output is a diff/artifact; applying it to
  a real repo is gated). LLMs still never touch live FS directly — Hard Rule #1 preserved.
- **Deliverable shape:** spec **and** plan per module, all up front (this arc). Plans are TDD task
  lists; re-validate a module's plan against `main` right before building it (the spine moves).

## The two data classes (from foundation — which table owns the truth)

| Module | Owns truth in | Emits awareness event |
|---|---|---|
| Tasks, Notes, Recipes, Documents, Calendar(local) | its **own CRUD table** | `task.*`, `note.*`, `recipe.*`, `document.*`, `calendar.event_*` |
| Email cache, Calendar(Google mirror) | a **read-mirror cache** (re-syncable, not truth) | `mail.*`, `calendar.synced` |
| Deep research, Code(OpenCode) | a **run/session record** (the harness log) | `research.*`, `code.session_*` |
| Memories UI, Routines UI | nothing new — **read existing** operational tables | — |

## Migration ledger (assign these; latest on `main` is `0018_reminders`)

| # | Migration | Module |
|---|---|---|
| 0019 | `app_sessions` | Shell (session login) |
| 0020 | `tasks` | Tasks |
| 0021 | `notes` | Notes |
| 0022 | `documents` | Document editor |
| 0023 | `recipes` | Recipes |
| 0024 | `mail_accounts` + `mail_cache` | Email |
| 0025 | `calendar_accounts` + `calendar_events` | Calendar |
| 0026 | `research_runs` | Deep research |
| 0027 | `model_prefs` | Model cookbook |
| 0028 | `code_sessions` | Code (OpenCode) |

Memories UI / Routines UI add **no migration** (they read `memories`/`user_facts` and `routines`).
Reconfirm the next free number against `migrations/versions/` at build time — others may have landed.

## Shared module template (every module conforms — from foundation)

**Backend:** CRUD table (`schema_version`, stable `entity_ref` `note:<id>`/`task:<id>`/…) · a small
gated tool-set (`<module>.create/update/delete/…`, graded: reversible+low-risk+on-box → **auto-run**;
irreversible/external/infra → **gated**) · a light awareness event on significant change · a pgvector
search hook (reuse `memory` retrieval) · a read accessor for the conversation agent's context.
**Frontend:** a route + nav entry in the shell · a panel component · a Cmd-K/global-search provider ·
theme tokens. **Cross-cutting (free):** linking via `entity_ref`+`correlation_id` (no graph DB);
cross-module AI actions ("email → task", "research → note", "recipe → shopping list → tasks"); the
composed daily brief assembles across modules; voice everywhere.

Every new boundary object ships: Pydantic model, `schema_version`, `correlation_id`/`causation_id`
where it rides the spine, validation, and a test (CLAUDE.md token rules).

## Build order + go/no-go gates (each step shippable & reversible)

1. **Shell + module framework + session login** — the template + the "one place" frame. *Gate:* login
   works; the existing modules (chat, torrents, etc.) render inside the shell; a "hello" demo module
   proves the backend+frontend template end-to-end; theme switch works. **Build the template here so
   every later module is a fill-in-the-blanks.**
2. **Quick wins on the spine (parallelizable):** **Tasks → Notes → Memories UI → Routines UI.** Each
   *Gate:* CRUD + auto-run tools + awareness event + search + panel; a cross-module action works
   (e.g. "remind me" → task). Lowest risk; proves the template four times.
3. **Deep research + Document editor** (the wow pair; router-backed). *Gate:* a research query runs the
   bounded harness (plan→fan-out→synthesize, step/cost caps) and lands a markdown doc; the doc editor
   opens/edits/AI-co-writes it; replay still pinned local.
4. **Recipes.** *Gate:* manual CRUD + URL→structured import (one inference) + "recipe → shopping list
   → tasks" cross-module action.
5. **Email client** (biggest). *Gate:* IMAP read+triage+search inbox; gated compose/send (mode ladder
   respected); "email → task/calendar" actions; daily-brief includes important mail. Spike IMAP first.
6. **Calendar (Google OAuth read-mirror + local editable).** *Gate:* OAuth connect, real Google events
   mirror read-only; local events CRUD (auto-run); daily-brief includes today; "email → calendar" works.
7. **Model cookbook / per-action picker.** *Gate:* UI to view+set per-action/per-routine backend;
   presets ("cookbook"); persisted in `model_prefs`; honored by the router's resolution precedence.
8. **Code module (OpenCode).** *Gate:* spike headless `opencode` in a throwaway worktree; a coding task
   produces a reviewable diff; **applying** the diff to a real repo is gated; nothing touches live FS
   un-gated. Last because it's the heaviest reconciliation with Hard Rule #1.

## Cross-cutting acceptance (the payoff — verify after step 4 and again at the end)

- **Linking:** an email → task → calendar event → note → doc are all reachable by `entity_ref`; the
  causal timeline (`correlation_id`) shows the chain. No graph DB.
- **Daily brief:** the morning push composes calendar(today) + tasks(due) + important mail + research
  digest + homelab health (extends the existing routines/ntfy path).
- **Voice:** "add milk to the list", "what's on today", "summarize my inbox" route to module actions.
- **Hard Rules:** #1 boundary intact (graded gate, never raw FS/shell to a model); #2 one-shot
  (research/code are deterministic harnesses); #5 replay pinned `local`; everything carries
  `schema_version`.

## Non-goals (whole arc)

No image editor. No public exposure / multi-user / external API. No autonomous agent loops (only
bounded deterministic harnesses). No graph DB. No 2-way external sync in v1 (Google calendar is
read-mirror; no write-back). No reverse-engineered LLM APIs. OpenCode never operates on live repos
un-gated — only isolated worktrees, diff-as-artifact.
