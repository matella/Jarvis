# Phase 3 (MVP) — Code Intelligence (design spec)

> Date: 2026-05-29 · Phase 3, first sub-project. Index the homelab compose repos (remote,
> over SSH) into the vector store and answer questions over them with the coder model.
> Read-only — the agent never edits files (deterministic boundary holds).

## Secret safety (Hard Rule 1) — first-class
Homelab compose repos hold secrets (VPN creds, API keys). Secrets must never reach the DB or
the model, even on a local-only homelab:
- **Exclude** secret files: `.env*`, `*.key`, `*.pem`, `*.crt`, `*.p12`, `*secret*`,
  `*credential*`, `id_rsa*`.
- **Allowlist** indexable types: `.yml/.yaml`, `Dockerfile`, `.conf`, `.toml`, `.sh`, `.md`.
- **Redact** secret-looking assignments (`...password|secret|token|api_key|private_key|auth... :
  <value>` → `<redacted>`) before storage/inference. Unit-tested.

## Decisions
- Target: **homelab compose repos** on the remote (default root `/home/matella/homelab`),
  read over SSH (reuses `remote_ssh`).
- **Dedicated `code_chunks` table** (migration 0006).
- **Read-only Q&A** coding agent (no change proposals — that's a later sub-project).

## Schema — migration 0006
`code_chunks(id chk_<ulid> PK, repo text, path text, start_line int, end_line int, content text,
embedding vector(768), indexed_at timestamptz)`; indexes on `repo` and HNSW cosine on embedding.
Re-index = delete repo's chunks + re-insert (current snapshot). Derived store (not event-sourced).

## Components
- **`ingest/code_index.py`**:
  - `_list_files(remote_ssh, root)` (ssh find), `_read_file` (ssh `head -c <max>` size guard).
  - `_is_secret_path` / `_is_indexable` / `_redact` / `_chunk` (N-line windows, default 60) — pure,
    unit-tested.
  - `index_repo()` — list → filter (indexable, non-secret) → read → redact → chunk → `embed_many`
    → replace repo's chunks atomically.
  - store: `insert_chunks`, `search_chunks(conn, qvec, k, repo)`, `delete_repo`.
- **`models/router.embed_many(texts)`** — bulk embedding under ONE semaphore hold, emits ONE
  summary `inference.completed` (batch=N), not one per chunk (no log flooding).
- **`agents/coder.py`** — `ask(question) -> CodeAnswer{question, answer, sources}`: embed question
  → `search_chunks` → assemble cited excerpts → `router.chat(role="coder")` → answer + `path:lines`
  sources. One-shot.
- **config**: `code_repo_path=/home/matella/homelab`, `code_repo_name=homelab`,
  `code_chunk_lines=60`, `code_max_file_bytes=200000`.
- **CLI**: `jarvis code index`, `jarvis code ask "..."`, `jarvis code search "..."` (retrieval-only).
- **ids**: add `CHUNK = "chk"`.

## Testing → acceptance
- **Unit** (no DB/ssh/model): `_is_secret_path` (excludes .env/.key/secret/id_rsa), `_is_indexable`,
  `_redact` (password/private_key/token values → redacted; `image: nginx` untouched), `_chunk`
  (line windows); `coder.ask` assembly with mocked embed/search/chat → answer + sources.
- **Integration** (DB): `insert_chunks` + `search_chunks` round-trip with a synthetic 768-vec;
  `embed_many(["x"])` returns a 768-vec (real Ollama). Skips if unavailable.
- **Live acceptance**: `jarvis code index` indexes the homelab repos (spot-check: no `.env`/secrets
  in `code_chunks`, secret values redacted); `jarvis code ask "how is qbittorrent networked?"`
  → coder model answers from real compose chunks, citing files (e.g. network_mode service:gluetun).

## Deferred (later Phase 3)
git/commit awareness, CI ingestion, deployment analysis, code-change proposal intents, symbol-aware
chunking.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
