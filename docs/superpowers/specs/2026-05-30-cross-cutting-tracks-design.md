# Cross-cutting tracks — detailed spec (layer in alongside Phases 6–11)

> Date: 2026-05-30 · Ongoing capabilities that compose with the phases rather than blocking them.

## A. Scheduled routines / proactive briefings
- **`routines/`** + `routines` table (id, name, schedule (cron-ish), action (a query/plan/summary
  spec), enabled, last_run). A daemon worker (`routine_scheduler`) fires due routines (change-aware,
  not naive — respects the kill switch/maintenance). Actions reuse existing capabilities (summarize,
  correlate, search, connectors) and produce a `routine.completed` event + optional notification.
- **CLI:** `jarvis routine add/list/run`. Example: "morning briefing" → overnight incidents + mail
  digest, delivered via notifier/voice.
- **Accept:** a routine fires on schedule, runs a grounded summary, notifies; respects maintenance.

## B. Feedback loop + eval/replay harness
- **Feedback:** operator rates proposals/incidents (👍/👎) in the console → `feedback` events. This
  is the training signal for **adaptive attention** (tune notifier/reactor thresholds by entity/type
  using approve/reject/execute + outcome history).
- **Eval/replay harness:** `eval/` — re-run stored `context_ref`s through the current model/agent and
  diff against the recorded decision; a regression gate run on every model/agent change (flag drift,
  don't fail on expected nondeterminism). Golden cases for summarizer/correlator/proposer.
- **Accept:** ratings recorded + queryable; the harness reports decision drift across a model swap.

## C. Richer observability ingest
- **`ingest/prometheus.py`** (scrape) + **`ingest/loki.py`** (logs) behind the same event/metrics
  spine → far sharper correlation/root-cause than docker stats alone. Logs especially unlock
  log-pattern incidents. **Accept:** Prometheus targets sampled into `metrics`; a log spike surfaces
  as an event that correlation can use.

## D. Memory governance
- A console view + CLI to **list / forget / consolidate** memories, summaries, playbooks; memory
  **consolidation** (compact old episodic summaries into higher-level ones) ties into the snapshot/
  compaction work (5.5a). **Accept:** forget a memory; consolidate a window of summaries into one.

## Notes
Each is independently shippable; prioritize by what the phases surface (routines + feedback are the
highest-leverage once 6a/6b exist). All obey the same boundary/observe/replay/local-first rules.
