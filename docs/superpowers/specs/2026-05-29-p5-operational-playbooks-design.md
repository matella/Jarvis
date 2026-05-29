# Phase 5 — Operational Playbooks (design spec)

> Date: 2026-05-29 · Phase 5 (ambient). Procedural memory (ARCHITECTURE 8.3): the operator
> teaches Jarvis known fixes; the infra agent retrieves the relevant playbook(s) by similarity
> and grounds its proposals in operator knowledge, not just model priors. Activates the
> persistent-memory pillar (pgvector) we built at M1.

## Decision
Dedicated `playbooks` table (0009), retrieved by embedding similarity and injected into the
infra agent's `propose_intent` context.

## Schema — migration 0009
`playbooks(id pb_<ulid> PK, title, when_to_use, procedure, embedding vector(768), created_at)`
+ HNSW cosine index.

## Components
- **`playbooks/models.py`** — `Playbook {id, title, when_to_use, procedure, created_at}`
  (embedding is a stored retrieval index, not a domain field).
- **`playbooks/repository.py`** — `add_playbook(conn, pb, embedding)`, `list_playbooks`,
  `search_playbooks(conn, query_vec, k)` (cosine; pure SQL — the model layer embeds).
- **`agents/infrastructure.py`** — `propose_intent` embeds a situation query, `search_playbooks`,
  and `_playbook_section(hits)` appends a "Relevant playbooks" block to the prompt; the system
  prompt is told to follow them when relevant. The stored `context_ref` includes the playbooks
  (so `explain` shows what guided the decision).
- **CLI**: `jarvis playbook add TITLE PROCEDURE [--when ...]` (embeds title+when, stores),
  `jarvis playbook list`.

## Testing → acceptance
- **Unit**: `Playbook` id prefix; `_playbook_section` rendering (hits → block, empty → "").
- **Integration** (DB): `add_playbook` + `search_playbooks` round-trip with synthetic 768-vecs
  (nearest returned); embedding dim via `router.embed` is 768.
- **Live**: `jarvis playbook add` a gluetun-routing playbook → a container-down `propose_intent`
  retrieves it (the stored context shows "Relevant playbooks"), grounding the proposal. Cleaned up.

## Deferred (rest of Phase 5)
auto-correlation; adaptive attention; wiring playbooks into the correlator too.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
