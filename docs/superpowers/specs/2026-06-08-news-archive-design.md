# World News — day-by-day edition archive

**Date:** 2026-06-08 · **Status:** approved, building

## Goal
Stop discarding past editions. Keep a permanent, browsable archive: each day is a frozen "edition";
today's fills live. Page-turn (‹ Hier / Demain ›) between days + an `/archive` index to jump anywhere.

## Edition model
Every story belongs to the calendar day (Europe/Brussels) it was **first pooled** (`created_at`).
One story → one edition (the day it broke). Today's edition grows as stories are pooled; past days
are frozen automatically (nothing new gets their date). Known behaviour: a story that develops over
several days stays in its break-day edition (newspaper-authentic); the cross-edition "follow the
thread" timeline is a later feature.

## Backend (Jarvis publish)
- Add `edition_date date` (+ index) to `published_stories`.
- Publish writes **all** engine stories (not just the recent 80), each tagged
  `edition_date = date(created_at AT TIME ZONE 'Europe/Brussels')`. Reconcile only removes a
  published story whose engine story is gone (with keep-everything retention, that's none) — the
  past is no longer thrown away.
- O(all stories) per cycle; fine at current volume. Incremental publish is a future optimisation.

## Frontend
- Extract a reusable **`<Edition>`** server component (masthead with the edition's date, page-turn
  nav, lead, sections, items, colophon) — the front page and every archived day render identically.
- Routes:
  - `/` → latest edition (today, live). `Demain` disabled.
  - `/edition/[date]` → that day's frozen edition, with ‹ Hier / Demain › to the adjacent
    **non-empty** dates + an Archives link.
  - `/archive` → all editions grouped by month with story counts; click to jump.
  - story pages unchanged + a "back to its edition" link.
- lib accessors: `latestEditionDate()`, `getEdition(date)`, `adjacentEditions(date)` (prev/next
  non-empty), `editionDates()` (archive index). `Story` gains `edition_date`.

## Out of scope (next features)
Cross-edition story threading + synthesis-history snapshots (the "how it evolved" timeline).
