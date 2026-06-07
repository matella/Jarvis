# World News (Jarvis-native) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Jarvis a real `news` capability — scrape sources, pool/dedup into stories, AI-summarize (tier A) and synthesize the day's top stories (tier B), all queryable/presentable through Jarvis, with a standalone Next.js reading site as a second face.

**Architecture:** Scraper (sensor) → Jarvis spine event → reactor stores/embeds/pools/summarizes (BACKGROUND priority) → daily routine synthesizes top-N by independent-source coverage → both faces (Jarvis cards/voice + Next.js site) read one shared store. Python brain; Rust only at a *proven* hot edge.

**Tech Stack:** Python 3.11, Pydantic, psycopg, Postgres + pgvector, Redis Streams (spine), Ollama (`qwen3:1.7b` tier-A / `qwen3:8b`|Claude tier-B), `bge-m3` multilingual embedder (CPU), `trafilatura` (readability), `feedparser` (RSS). Spec: `docs/superpowers/specs/2026-06-07-world-news-jarvis-hybrid-design.md`.

**Reference patterns (follow these exemplars):**
- Module shape: `jarvis/tasks/{models,repository}.py`
- Reactor enrich-on-event (the closest analogue): mail triage in `jarvis/mail/` + the daemon reactor
- Webhook ingest: `jarvis/gateway/webhooks.py`
- Daily action: `jarvis/routines/{models,scheduler}.py` (`ActionKind`, `run_action`)
- Present route: `jarvis/agents/conversation.py` (`_present_target`, `_present_hots` as a template)
- Boundary rules: `CLAUDE.md` (schema_version, correlation/causation, event-log-is-truth, external-content-is-data)

**Scope note:** This plan covers the **Jarvis backend** (Milestones 1–3). The **Next.js site (Milestone 4)** is a separate subsystem and gets its own plan once the read API exists. Each milestone below leaves the system working and testable.

---

## Chunk 1 — Milestone 1: the `news` module (the brain)

After this chunk, an article POSTed to the ingest endpoint is stored, embedded, pooled into a story, and tier-A summarized; *"what's the world news?"* returns real cards; semantic search works. No scraper yet (tests drive ingest directly).

### Task 1.1: Schema + migration

**Files:**
- Create: `migrations/versions/<rev>_news_tables.py` (generate with `alembic revision -m "news tables"`)
- Test: `tests/integration/test_news_repo.py` (smoke: tables exist, insert+read round-trips)

Tables (see spec "Data model"). `news_articles`: id, source, origin_id, url, canonical_hash UNIQUE, lang, title, body, published_at, summary, topic, region, embedding `vector(1024)` (bge-m3 dim), story_id FK, schema_version, recorded_at. `news_stories`: id, lang, title, synthesized_body, claims_json JSONB, disagreements_json JSONB, source_count, origin_count, top_at, created_at, updated_at, embedding `vector(1024)`. Indexes: `canonical_hash` unique; ivfflat on both embeddings; `(lang, published_at)`.

- [ ] **Step 1:** Write the failing integration test (insert an article + a story, read them back).
- [ ] **Step 2:** Run it → FAIL (relation does not exist). `pytest tests/integration/test_news_repo.py -v`
- [ ] **Step 3:** Write the alembic migration creating both tables + indexes.
- [ ] **Step 4:** `alembic upgrade head`; run test → PASS.
- [ ] **Step 5:** Commit `feat(news): schema + migration for articles/stories`.

### Task 1.2: Pydantic models

**Files:** Create `jarvis/news/__init__.py`, `jarvis/news/models.py`; Test `tests/test_news_models.py`

`NewsArticle` + `NewsStory` Pydantic models mirroring the tables, each with `schema_version: int = 1`, `entity_ref` property (`news_article:<id>` / `news_story:<id>`), and a `canonical_hash` helper (normalize URL: strip query/fragment+lowercase host; fallback to normalized title). Follow `jarvis/tasks/models.py`.

- [ ] **Step 1:** Failing unit test: `canonical_hash("https://x.com/a?utm=1")` == `canonical_hash("https://x.com/a")`; entity_refs correct.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement models + helpers.
- [ ] **Step 4:** Run → PASS. Step 5: commit `feat(news): pydantic models`.

### Task 1.3: Repository (CRUD + dedup + pgvector search)

**Files:** Create `jarvis/news/repository.py`; Test `tests/integration/test_news_repo.py` (extend)

Functions: `upsert_article(conn, art)` (ON CONFLICT canonical_hash DO NOTHING → returns existing or new; **idempotent**), `get_article`, `recent_stories(conn, *, limit, lang=None, topic=None)`, `create_story`/`attach_article_to_story`/`bump_story_counts`, `search(conn, query_vec, *, limit)` (pgvector cosine over stories+articles), `top_stories_since(conn, since, *, limit)` (rank by `origin_count` × recency).

- [ ] Step 1: Failing tests — upsert is idempotent (same canonical_hash twice → one row); search returns nearest by vector; top_stories ranks by origin_count.
- [ ] Step 2: FAIL. Step 3: implement (follow `jarvis/mail/repository.py` for the SQL+pgvector style). Step 4: PASS. Step 5: commit `feat(news): repository with idempotent upsert + vector search`.

### Task 1.4: Multilingual embedder (bge-m3, CPU)

**Files:** Create `jarvis/news/embedding.py`; Test `tests/test_news_embedding.py`

`embed_news(text) -> list[float]` via Ollama (`bge-m3`, routed through the scheduler at BACKGROUND priority). Dim 1024. Pull model on box later. Test mocks the model call; assert correct role/model + vector length.

- [ ] Steps 1–5 (TDD + commit `feat(news): multilingual embedder`).

### Task 1.5: Pooling (dedup → cluster)

**Files:** Create `jarvis/news/pooling.py`; Test `tests/test_news_pooling.py`

Pure-ish logic: `find_or_make_story(conn, article, *, sim_threshold=0.82, window_h=48)` — same `lang`, embedding cosine ≥ threshold, `published_at` within window → attach; else new story. `collapse_origin(articles)` — near-identical bodies (e.g. ≥0.97 cosine or shared canonical body hash) share one `origin_id` so wire copies count once. `count_independent_origins(story)`.

- [ ] Step 1: Failing tests with synthetic embeddings — two near-identical articles → same story & same origin_id; a dissimilar one → new story; origin count collapses wire dupes.
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `feat(news): pooling + origin-dedup`.

### Task 1.6: Ingest event + webhook

**Files:** Modify `jarvis/gateway/webhooks.py` (+ route in `jarvis/gateway/app.py`); Create `jarvis/news/ingest.py`; Test `tests/test_news_ingest.py`

`POST /webhooks/news` accepts `{source, url, lang, title, body, published_at}`, computes `canonical_hash`, stores the body in PG, and emits a `news.article_scraped` event (schema_version + correlation/causation + occurred/recorded_at) carrying a **body reference, not the text**. Idempotent on canonical_hash. Auth via the existing webhook token. Follow the Jellyseerr webhook in `webhooks.py`.

- [ ] Step 1: Failing test — POST an article → one event emitted with correct schema; re-POST → no duplicate.
- [ ] Step 2–5 (TDD + commit `feat(news): ingest webhook + article_scraped event`).

### Task 1.7: Reactor — enrich on event

**Files:** Create `jarvis/news/reactor.py`; wire into the daemon reactor registration; Test `tests/test_news_reactor.py`

On `news.article_scraped`: load article → `embed_news` → `find_or_make_story` (pool) → if this is the story's representative, run **tier-A** (`qwen3:1.7b`, BACKGROUND): summary + `topic` + `region`, in the article's language. **Prompt-injection guard:** article text goes in a delimited UNTRUSTED-DATA block; the model is told it's content to summarize; output only writes the summary projection. Mirror mail triage. Bound LLM calls: summarize the representative only.

- [ ] Step 1: Failing test (mocked LLM + embedder) — event → article stored, pooled, representative summarized+tagged; a duplicate article does NOT trigger a second summary.
- [ ] Step 2–5 (TDD + commit `feat(news): reactor — embed/pool/tier-A`).

### Task 1.8: Present route + capability + config + search

**Files:** Modify `jarvis/agents/conversation.py` (`_present_target` add `news` pattern `\b(world news|the news|headlines)\b`; `_present_news`), `jarvis/capabilities.py` (replace the stub `world news` cap with the real one), `jarvis/config.py` (news settings), `jarvis/eval/cases.py` (routing cases); Test `tests/test_news_present.py`

`_present_news(conn, utterance)`: if "about X"/search terms → `embed_news(query)` + `repository.search` → cards; else `recent_stories`/`top_stories` → cards via `auto_artifact`. Replace the old `world_news` stub connector/route. Add eval cases ("what's the world news" → present:news; "news about the EU" → present:news; ensure a coding "news" false-positive stays llm).

- [ ] Step 1: Failing tests (mocked repo) — present returns story cards; search path embeds the query; eval cases route correctly.
- [ ] Step 2–5 (TDD + `make eval` green + commit `feat(news): present route + semantic search + capability`).

### Task 1.9: Chunk verification

- [ ] Run `ruff check jarvis tests` + `pytest -q -m "not integration"` + `python -m jarvis.eval.behavior` → all green.
- [ ] Commit any fixes. This chunk is done when ingest→pool→summarize→present works end-to-end against mocked models.

---

## Chunk 2 — Milestone 2: scraping (the sensor)

After this chunk, real RSS sources flow into the ingest endpoint hourly, and *"what's the world news?"* returns real headlines.

### Task 2.1: Source config
- [ ] `jarvis/news/sources.py`: the v1 starter list (Reuters, AP, BBC, Guardian, Al Jazeera; RTBF, Le Soir, La Libre, VRT NWS, Politico Europe) with `{name, rss_url, lang}`. Test: list loads, langs valid.

### Task 2.2: Fetcher (efficiency-first, polite)
- [ ] `jarvis/news/fetch.py`: `feedparser` per source with **conditional GET** (store/send ETag + If-Modified-Since → skip unchanged), per-domain rate-limit, real User-Agent, **SSRF guard** (reuse `jarvis.security.egress` — block RFC-1918/internal), `trafilatura` readability with RSS-summary fallback. TDD with a fake feed fixture (no network); assert conditional-GET skips, SSRF blocks an internal URL, readability falls back.

### Task 2.3: Scrape routine
- [ ] Add `ActionKind.news_scrape` in `jarvis/routines/models.py`; handle in `routines/scheduler.py::run_action` → fetch all sources → POST new items to the ingest endpoint. Hourly schedule. TDD the dispatch (mocked fetch+ingest).
- [ ] Commit per task. Chunk verify: lint + tests green; deploy + a live smoke (real feeds → stories appear).

---

## Chunk 3 — Milestone 3: daily synthesis + briefing (tier B)

After this chunk, a daily routine writes synthesized, cited, disagreement-aware write-ups for the top-N stories and pushes a briefing.

### Task 3.1: Synthesis
- [ ] `jarvis/news/synthesis.py`: `synthesize_story(conn, story)` — gather the cluster's source texts, run **tier B** (`qwen3:8b`/Claude) under a grounded template: cite each claim to a source, fill `claims_json`, surface `disagreements_json`, write `synthesized_body` in the cluster's dominant language. **Untrusted-data framing** (prompt-injection). TDD with mocked LLM returning a structured object; assert citations + disagreements persisted.

### Task 3.2: Daily routine + digest
- [ ] `ActionKind.news_brief` → `top_stories_since(24h, limit=N)` → synthesize each (BACKGROUND, serialized) → push "Daily Briefing" via the existing ntfy notifier; mark `top_at`/seen-state so the next day doesn't repeat. Daily 07:00 schedule. TDD the selection + dispatch.
- [ ] Add a **news eval fixture** `tests/test_news_eval.py`: sample articles → assert clustering groups them, tier-A emits valid tagged summaries, tier-B cites sources.
- [ ] Commit per task; chunk verify + deploy + live smoke (briefing fires).

---

## Milestone 4 (separate plan): Next.js standalone site
Out of scope here. When the read API (Chunk 1's present/search, exposed via a small Jarvis news REST endpoint) is stable, write `docs/superpowers/plans/<date>-world-news-ui.md`: feed page, Deep/Debate story page, Ask-Jarvis embed, filters — matching the validated mockups in `world-news-full/.superpowers/brainstorm/`.

---

## Deploy notes
- Pull models on box: `bge-m3` (CPU), ensure `qwen3:1.7b`/`qwen3:8b` present (they are).
- New config in box `.env`: news enable flag, top-N (default 10), sim threshold, schedule times.
- Retire the Rust `api-gateway`/`ai-service` containers (decision 1); keep the Rust scraper repo parked.
- Per-milestone: `git push box main` + `make deploy`; verify via the live smoke for that milestone.

## Deferred / recommended (schedule when convenient)
Recency-weighted ranking refinements · retention/pruning job (raw bodies ~90d) · cross-language event grouping (v2) · coverage-spectrum/bias model · story timelines · audio briefing (Piper) · knowledge graph.
