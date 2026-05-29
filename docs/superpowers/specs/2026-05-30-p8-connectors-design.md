# Phase 8 — Connectors (read + act) + inbound webhooks — detailed spec

> Date: 2026-05-30 · External integrations behind the boundary. Read = ingest → events; act =
> capability-scoped Tools → gated Intents. Each connector is its own mini-milestone.

## Decisions
- **Connector interface:** `ingest()` (pull → normalized events/records, sanitized) + registered
  **act-Tools** (e.g. `mail.send`, `calendar.create_event`, `ha.set_state`). Secrets via
  `SecretsProvider`; all fetched content through `sanitize()` + `wrap_untrusted()`; outbound via the
  egress allowlist.
- **Order:** mail → calendar → feeds → Home Assistant. Plus **inbound webhooks** (push).
- **Untrusted content can shape a proposal, never bypass the gate** (the core safety property).

## Components
- **`connectors/base.py`** — `Connector` protocol (`ingest`, declared act-Tools), registry.
- **`connectors/mail.py`** — IMAP read → `mail.received` events (subject/from/snippet, sanitized;
  bodies in a store if needed); `mail.send` Tool (SMTP) → gated Intent.
- **`connectors/calendar.py`** (CalDAV), **`connectors/feeds.py`** (RSS → `feed.item` events),
  **`connectors/homeassistant.py`** (REST/WS; `ha.*` Tools for scenes/devices/states).
- **Inbound webhooks:** gateway `/inbound/<source>` (signature-verified) → maps GitHub/Grafana/HA
  pushes to events on the spine — the *push* complement to *pull*.
- **daemon:** connector ingest as periodic workers (cadence per connector).
- **config/secrets:** per-connector creds via `SecretsProvider`; enabled-connectors list.

## Testing → acceptance
- **Unit:** mail/feed/calendar parse → normalized events (sanitized, PII redacted); act-Tools
  registered with proper contracts; webhook signature verification + mapping; injection content →
  no ungated action.
- **Integration (guarded):** against a test IMAP/SMTP (or a local mailhog) ingest + send; a posted
  webhook lands as an event; HA against a test instance toggles a safe entity via a gated intent.
- **Live:** ingest mail → queryable + feeds correlation; "reply to X that …" → gated `mail.send`
  you approve; a Grafana alert webhook correlates; "turn on office lights" → gated `ha` intent.

## Dependencies
5.5c (secrets/egress/sanitize), 6a (gateway for webhooks; chat to drive sends), M4 gate.
Home Assistant is in the homelab — high-value, fun flagship connector.
