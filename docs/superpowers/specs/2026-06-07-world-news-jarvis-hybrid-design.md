# World News — Jarvis-native hybrid news system

## Vision
A self-hosted news experience where the **scraper is a sensor, Jarvis is the brain, and there are
two faces**: a standalone Next.js reading site and Jarvis (conversational + cards + a daily
briefing). Nothing AI- or storage-related is built twice. The long-horizon north star ("V20") is a
finite, calm, story-centric, AI-synthesized, conversational newsroom (audio briefings, coverage
spectrum, story timelines, "you're caught up"). V1 is the seed of that, not a different thing.

## Locked decisions (from brainstorming)
- **Hybrid**: standalone UI + Jarvis, over one shared core.
- **Tiered AI (C)**: tier A = a cheap summary for every (representative) article; tier B = a
  multi-source *synthesis* for the day's top stories.
- **Tier-B trigger (A+D)**: each day, synthesize the **top-N clusters ranked by # of distinct
  independent sources**. Predictable GPU budget; surfaces genuinely big stories.
- **Scope (C)**: broad mix — world English majors + Belgian/EU (FR/NL) feeds.
- **Language**: keep each story in its **source language** — no translation. Same event in EN+FR =
  two stories in v1 (cross-language grouping deferred to v2).

## Recommended fork resolutions (CONFIRM on review)
1. **Retire the Rust `api-gateway` and `ai-service`; v1 scraping folds into Jarvis.** Jarvis already
   has an RSS feeds connector, an LLM boundary, pgvector, and the scheduler. Extending Jarvis's
   feeds pipeline (Python) with readability + politeness is simpler than running two extra Rust
   services that duplicate Jarvis. → **world-news repo v1 = the Next.js UI only**, pointed at a
   Jarvis news read API. The Rust scraper is parked as an optional high-performance swap-in later.
2. **Cross-language event grouping = v2.** v1 keeps per-language stories.
3. **Dedicated multilingual embedder for news** (e.g. `bge-m3` on CPU), with news vectors stored in
   the news tables — separate from Jarvis's existing `nomic-embed-text` search index, so FR/NL
   search/clustering is good *without* a global embedding-dimension migration.

## Architecture & data flow (event-driven, honoring the spine)
```
Jarvis feed poller (hourly, extended)
  → fetch RSS (world EN + BE/EU FR/NL) + readability extraction + politeness
  → POST internal ingest → `news.article_scraped` event (schema_version, correlation/causation)
        │  (idempotent on canonical_hash; body stored in PG, reference in the event)
        ▼
Jarvis reactor (BACKGROUND priority, preempted by interactive chat/voice):
  store article → embed (multilingual) → POOL into a story cluster
     (same-language, cosine ≥ τ, within 48h; collapse syndicated/wire copies to one ORIGIN)
  → tier A summary + topic/region tags on the cluster REPRESENTATIVE only (not every dup)
        ▼
Jarvis routine (daily 07:00):
  rank stories by # distinct independent sources × recency → top-N
  → tier B synthesis: grounded in source texts, each claim CITED, disagreements surfaced
  → push "Daily Briefing" (ntfy; later Piper audio)
        ▼
  ┌──────── both faces read the shared store via a Jarvis news read API ────────┐
  Next.js site: feed · story page (synthesis + sources + spectrum) · filters
  Jarvis: "what's the news" → cards · "news about X" → semantic search · "brief me" → digest
```

## Data model (Jarvis Postgres + pgvector)
- **`news_articles`**: id, source, origin_id (syndication-collapsed), url, canonical_hash (unique),
  lang, title, body (full text), published_at, summary (tier A), topic, region, embedding,
  story_id, schema_version, recorded_at.
- **`news_stories`**: id, lang, title, synthesized_body (tier B, nullable), claims_json (claim →
  source citations), disagreements_json, source_count, origin_count, top_at, created_at,
  updated_at, embedding.

## Ingest contract (frozen shape)
`news.article_scraped` event payload: `{source, url, canonical_hash, lang, title, body_ref,
published_at}` + standard `schema_version`, `correlation_id`, `causation_id`, `occurred_at`,
`recorded_at`. Idempotent on `canonical_hash` (retries are no-ops). Full body stored in PG; event
carries a reference, not the text (keeps the spine lean).

## Hard requirements (must-haves)
- **Prompt-injection defense**: scraped text is UNTRUSTED DATA. It enters tier-A/B prompts inside a
  clearly delimited data block; the model is instructed it's content to summarize, never
  instructions; its output only writes a summary projection — it can NEVER trigger an action.
- **SSRF guard on fetch**: feed/article URLs go through egress checks — block RFC-1918/internal/
  link-local targets; allowlist source domains.
- **Background scheduling + backpressure**: tier-A/B run at BACKGROUND priority (interactive chat
  always preempts). Bursts queue in a `pending` state and drain at GPU speed.
- **Syndication-aware coverage**: collapse wire/near-identical copies to one ORIGIN; rank by
  distinct independent outlets, not raw article count.
- **Versioned, idempotent boundary** (Jarvis rule): every event/row carries schema_version +
  causal ids; ingest dedups on canonical_hash.

## Models
- Tier A (representative per cluster): `qwen3:1.7b` — fast/cheap on the steady drip.
- Tier B (top-N/day only): `qwen3:8b` or Claude — quality; ~10/day so affordable.
- Embedding: multilingual (`bge-m3`/`multilingual-e5`), CPU. All routed via Jarvis's one-model
  scheduler → no GPU contention with interactive work.

## Recommended (not v1-blocking)
- **Recency-weighted ranking + seen-state** so briefings aren't stale or repetitive.
- **Retention policy**: prune raw bodies ~90d, keep story summaries longer, expire embeddings.
- **News eval fixture**: sample articles → assert clustering groups them, tier-A emits valid tagged
  summaries, tier-B actually cites sources. A regression net for AI quality.

## The two faces
- **Jarvis (built first — the brain + most value):** a `news` module (tables + ingest + pipeline +
  pgvector search), present route ("what's the world news" → top-story cards), semantic search
  ("news about X"), and the daily briefing routine (+ntfy/Piper). Capability registry + config
  (`WORLD_NEWS_*`) updated; the existing stub connector is replaced by the real module.
- **Standalone Next.js site:** the reading experience (feed, story page with synthesis + cited
  sources + coverage spectrum, filters by topic/region/lang/recency), talking to the Jarvis news
  read API. Reading modes (Glance/Brief/Deep/Debate/Explainer) and audio briefing are the V20 path.

## Build order (each testable + deployed)
1. **Jarvis `news` module**: schema + ingest + store/embed/pool + tier-A(+tags) + present + search.
2. **Feed scraping in Jarvis**: real RSS (configured sources) + readability + politeness → ingest.
   → after 1+2, *"what's the world news?"* returns real, summarized, searchable headlines.
3. **Daily synthesis routine** (tier B, grounded/cited/disagreement-aware) + briefing digest.
4. **Next.js site** against the Jarvis news read API (feed + story pages + filters).
5. *(V2)* cross-language grouping · coverage-spectrum/bias · story timelines · audio · knowledge graph.

## V20 horizon (the trajectory, not v1 scope)
Story-centric & finite ("you're caught up") · synthesis-as-hero with agreement/disagreement &
citations · Jarvis-in-the-page conversation · time-budget reading modes · story timelines &
"what changed" · multimodal (audio/charts/maps) · personal-without-bubble · entity/knowledge graph ·
ambient surfaces (morning brief, situation room, weekly recap) · calm editorial design. Most of these
are "turn the crank" on the v1 core; only the bias-spectrum model, knowledge graph, and polished
multimodal layer need genuinely new capability.

## Open forks to confirm
- **Fork 1**: retire the Rust services (api-gateway + ai-service) and fold scraping into Jarvis for
  v1? (Recommended.) Or keep the Rust scraper as the sensor?
- **Fork 2**: multilingual embedder for news now (recommended) vs accept weaker FR/NL with the
  existing embedder?
