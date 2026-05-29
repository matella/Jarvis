# Phase 3 — Deployment / Image-Change Awareness (design spec)

> Date: 2026-05-29 · Phase 3 (git/CI awareness dropped — the homelab isn't git-tracked).
> Detect container redeploys (image/digest changes) deterministically and surface them in the
> journal + correlation, so "the incident followed a redeploy" becomes visible.

## Decision
A deterministic builder (like topology/metrics): inspect container images, diff against a
stored baseline, emit `container.deployed` events on change. No git/CI needed.

## Schema — migration 0007
`container_images(entity text PRIMARY KEY, image text, digest text, updated_at timestamptz)`
— the current image per container (baseline for diffing). Derived store.

## Components
- **`ingest/deploy.py`**:
  - `_inspect_images(context)` — `docker inspect --format {{.Name}}|{{.Config.Image}}|{{.Image}}`
    → (entity, image tag, image digest) per running container.
  - `_diff(current, baseline)` (pure) → list of deploy changes: digest changed = redeploy;
    first sighting = seed baseline (no event, avoids first-run flood).
  - `detect_deployments()` — inspect → diff → emit `container.deployed` per change → upsert baseline.
  - store: `get_baseline`, `upsert_images`.
- **`container.deployed`** event: severity info, source `deploy`, entity_ref `container:<name>`,
  payload `{image, digest, previous_image, previous_digest}`.
- **Journal**: include `container.deployed` events (a deploy is a significant operational happening).
- **Correlator**: fetch recent `container.deployed` events for a cluster's entities (same window)
  and render a "Recent deployments" section into the prompt → root-cause can cite a deploy.
- **CLI**: `jarvis deploy detect`, `jarvis deploy show` (baseline images + recent deploys).

## Testing → acceptance
- **Unit** (no docker/DB): `_diff` — new container seeds baseline (no change emitted); same
  digest → nothing; changed digest → one deploy change with previous/new.
- **Integration** (docker + DB): `detect_deployments()` runs; second immediate run detects 0
  (baseline stable); baseline rows written. Skips if unavailable.
- **Live acceptance**: run `deploy detect` to seed baseline; redeploy a throwaway container with a
  different image → `deploy detect` emits one `container.deployed`; it appears in `jarvis journal`;
  a burst correlated near it shows the deploy in the incident context.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.
