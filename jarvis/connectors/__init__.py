"""Connectors (Phase 8) — external integrations, behind the boundary.

Two directions, both safe by construction:
- **read**: `ingest()` pulls from a source and emits normalized, **sanitized** events onto the spine
  (external content is data, never instructions — it can shape a proposal, never bypass the gate).
- **act**: connectors register capability-scoped **Tools** (`mail.send`, `ha.set_state`, …) that are
  only reachable through a validated Intent + the M4 gate.

Secrets come from `security.secrets`; outbound calls go through the `security.egress` allowlist;
fetched text is run through `security.sanitize`. Importing this package registers the act-Tools.
"""

from jarvis.connectors import feeds as _feeds  # noqa: F401 — registers feeds connector
from jarvis.connectors import homeassistant as _ha  # noqa: F401 — registers ha.set_state
from jarvis.connectors import jellyseerr as _js  # noqa: F401 — registers jellyseerr.request/approve
from jarvis.connectors import mail as _mail  # noqa: F401 — registers mail.send
