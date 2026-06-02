# Email Client

> Date: 2026-06-02 · Personal-OS module (step 6; the biggest). A **connector + read-mirror cache**
> for reading/triage/search (the cache is re-syncable, **not** the source of truth) plus **gated**
> compose/send. Extends the existing `connectors/mail.py` (IMAP→events) into a full inbox. **Generic
> IMAP/SMTP, app-password** (locked decision — provider-agnostic, no OAuth). Inherits the foundation.

## Access model (locked)

One IMAP (read) + SMTP (send) path that works with Gmail app-passwords, Fastmail, Proton-bridge, any
host. **Read+triage+search = ungated** (it's a mirror of your own mail). **Compose/send = gated**
(external effect, irreversible — Evolution #2 puts send firmly on the gated side; the mode ladder
also governs: `observe` = dry-run only).

## Shape

- **Secrets:** `MAIL_IMAP_HOST/PORT/USER`, `MAIL_SMTP_HOST/PORT`, `MAIL_APP_PASSWORD` in the box
  `.env` via SecretsProvider — **never** in DB/git/logs. (Multi-account = a small `mail_accounts`
  row referencing an `.env` secret name; v1 may support one account, schema allows N.)
- **Migration `0024_mail`:** `mail_accounts(id, label, imap_host, imap_port, imap_user,
  smtp_host, smtp_port, secret_name, schema_version, created_at)` (NO password column — only the
  `.env` secret name) + `mail_cache(id, account_id, uid, message_id, thread_id, from_addr, to_addrs,
  subject, snippet, body_text, headers_json, flags, folder, received_at, triage_json, schema_version,
  entity_ref, synced_at)`. `entity_ref = "mail:<id>"`. The cache is a **mirror** (purge+re-sync safe).
  `ids.MAILACCT`/`ids.MAIL` prefixes.
- **Read connector** (`connectors/mail.py`, extend): periodic IMAP IDLE/poll → upsert `mail_cache` →
  emit `mail.received` (the existing event) for **new** messages; full bodies fetched on demand.
  Egress-guarded; bodies **sanitized + wrap_untrusted** (email is hostile input — never instructions).
- **Triage** (one one-shot inference per new message, **local**, grammar-constrained — reuse the
  existing mail/RSS noise classifier): `{category, importance, needs_reply, summary}` → stored in
  `triage_json`, drives the daily brief + a `mail.flagged_important` event. No loop.
- **Search:** index subject+snippet+body via the shared hook (`source=mail`) so mail is findable and
  in the conversation agent's context.
- **Send tools** (**gated**): `mail.compose` (draft — auto-run, it's just a draft document) +
  `mail.send` (gated; SMTP; `side_effects=true`, `idempotent=false`, `rollback=none`). A reply/
  compose may be **AI-drafted** (one inference → proposal in the composer; you edit + send through
  the gate). Model proposes; you send.

## Cross-module + AI (the payoff)

- **"email → task"** (`task.create`, `source_entity_ref=mail:<id>`), **"email → calendar event"**,
  **"email → note/document"**. **"draft a reply"** (one inference → gated send). **"summarize my
  inbox"** (triage digest). All ride `entity_ref` linking.
- **Daily brief:** important + needs-reply mail in the morning push (extends routines/ntfy).
- **Voice:** "any important email?", "reply to <sender> saying …" (drafts → gated send).

## Events / data

`mail.received` (existing), `mail.flagged_important` (`warning`), `mail.sent` (`info`,
`correlation_id` links to the triggering intent). Cache rows carry `synced_at`; a `mail.sync_failed`
(`failure_class`) on IMAP errors. No truth in the cache — re-sync rebuilds it.

## Frontend

Route `/mail` + nav + panel: folder/account switch, thread list (triage importance badges), reading
pane (sanitized HTML→text render), **composer** with AI-draft button + a **send confirmation** (the
gate), search. Cmd-K: "search mail", "compose", "summarize inbox". Theme tokens.

## Testing → acceptance

- **Unit:** IMAP fetch→`mail_cache` upsert (mocked IMAP); sanitize/wrap_untrusted on bodies; triage
  inference (mock scheduler) → `triage_json`; `mail.send` is **gated** (asserted via grading +
  mode ladder; `observe`=dry-run); AI-draft returns a proposal without sending; search indexing.
- **Integration (auto-skip, real account via env):** sync pulls recent mail; send a test mail
  through the gate; "email → task/calendar" links resolve; secrets never logged.
- **Frontend (vitest):** thread list + triage badges; reading pane; composer + AI-draft +
  send-confirm gate; Cmd-K.
- **Gate:** read+triage+search inbox; gated compose/send (mode-ladder respected); email→task/calendar
  actions; daily brief includes important mail; **no secret in any log/row**; suite + lint green.

## Plan (TDD)

1. Secrets + `0024_mail` migration (accounts w/o password + cache) + models + repository. Tests.
2. Extend `connectors/mail.py`: IMAP sync → cache upsert + `mail.received` + sanitize/wrap_untrusted. Tests (mock IMAP).
3. Triage one-shot (reuse classifier) → `triage_json` + `mail.flagged_important`. Tests (mock sched).
4. Search hook + conversation context accessor. Unit.
5. `mail.compose` (auto-run draft) + `mail.send` (gated, SMTP) + AI-draft proposal. Tests (gating + mock SMTP).
6. Cross-module: email→task/calendar/note/document; daily-brief important mail. Integration.
7. Frontend: panel (list/read/compose) + send-confirm gate + Cmd-K. vitest.
8. MAP.md (`connectors/mail`) + STATUS. Spike IMAP connectivity on the box **before** task 2.

## Non-goals

No OAuth (app-password only, v1). No HTML email composer (text/markdown→simple HTML). No
push/server-side rules engine beyond triage. No calendar invite parsing in v1 (email→calendar is a
manual action). No attachment editing (download/list only). No write-back of read/flag state to the
server in v1 (local triage only).
