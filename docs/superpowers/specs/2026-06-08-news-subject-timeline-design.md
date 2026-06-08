# World News — "follow a subject across days" timeline (saga thread)

**Date:** 2026-06-08 · **Status:** approved, building

## Goal
On a story page, show how that **subject** evolved across editions — a chronological thread of
related stories from other days. Uses the story embeddings we already store; no new infra, no LLM.

## Approach
Per-story similarity links (chosen over global thread_id clustering / LLM topic keys — simplest,
safe against mega-threads, retroactive on existing data).

## Backend (Jarvis)
- `repository.story_threads(conn, ids, *, k=6, max_distance, window_days=30)` → `{id: [related_id]}`
  via a pgvector lateral KNN (cosine `<=>`), excluding self, candidates within the window and below
  a distance threshold. Conservative threshold to avoid unrelated noise; tunable.
- `published_stories.related_ids text[]`; publish computes + stores it for each story.
- Cost is O(published stories) per publish (~426 now, fine). If the archive grows large, move the
  KNN to a periodic worker / scope to recent stories — noted, not needed yet.

## Frontend
- `lib.getThread(story)`: fetch the related published stories (id, title, edition_date, origin_count),
  add the current story, sort oldest→newest → the thread.
- Story page: a **"Suivi du sujet"** vertical timeline — date · headline per entry (current one
  highlighted), each linking through. Only shown when there's ≥1 related story (else hidden).
- `Story` gains `related_ids`.

## Data depth note
RSS gives only recent items, and editions are dated by pool-time, so we can't backfill 30 days from
current sources; the archive accumulates correct multi-day depth going forward. A historical backfill
(GDELT/paid API + publish-time dating) is a separate future project.

## Out of scope
Dedicated full-page timeline; global topic clustering; synthesis-history; historical backfill.
