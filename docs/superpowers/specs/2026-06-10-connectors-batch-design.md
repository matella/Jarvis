# Connectors batch — Pi-hole, Sonarr/Radarr, Actual Budget, GitHub (MCP-as-client)

**Date:** 2026-06-10 · **Status:** approved, building

## Scope
Four read-only data links, same pattern as existing connectors (egress-guarded fetch → typed dicts →
presenter; the LLM never calls them — deterministic code does). Conversation routing + capability
registry entries + tests for each.

- **Pi-hole (v6 API):** `connectors/pihole.py` — POST `/api/auth` (password) → sid → GET
  `/api/stats/summary` (queries today, blocked, %, clients) → best-effort logout. Config
  `PIHOLE_URL` (default host.docker.internal:8080) + `PIHOLE_PASSWORD` (self-served box-side from
  the pihole container's env — never displayed/committed).
- **Sonarr + Radarr:** `connectors/arr.py` — `/api/v3` with X-Api-Key: queue (downloading) +
  calendar (next 7 days). Keys self-served from each app's config.xml into the box .env.
- **Actual Budget:** `connectors/actualbudget.py` — v1 = `reachable()` (GET /info) + `authed()`
  (ACTUAL_PASSWORD set). Full budget client (actualpy) lands once the operator provides the
  password — same dormant-with-remedy state as Orpheus/Spotify. No new dependency until then.
- **GitHub via MCP-as-client:** `connectors/github.py` — MCP client (SDK already a dep) to the
  hosted GitHub MCP (`https://api.githubcopilot.com/mcp/`, Bearer GITHUB_PAT). Tool names resolved
  dynamically from `list_tools` (notifications / PR search), graceful error otherwise. Dormant
  until GITHUB_PAT is set + host egress-allowlisted. Deterministic: code picks the tools, not a
  model — MCP used as a data transport, so the execution boundary holds.

## Routing
`_PRESENT_PATTERNS` += pihole (pi-hole/dns/adblock), arr (sonarr/radarr/airing), budget
(budget/spending/finances), github (github/pull requests). All four present on mention (like
hots/orpheus). Presenters use accurate not-connected/dormant messaging + remedies.

## Out of scope
Write actions (pause Sonarr queue, whitelist a domain …) — would be Intents, later. Actual full
client + GitHub live verification until secrets exist.
