"""Model cookbook — per-action / per-routine backend choice + named presets (personal-OS module #9).

Closes the router arc: lets the operator pick which backend each action uses (e.g. claude for
`research.synthesize`, local for triage). It does NOT change the router's resolution algorithm — it
supplies the explicit `backend` value a caller passes; the hard overrides (breaker / budget /
schema → local) still win, so a `claude` pref can never defeat the safety net.
"""

from jarvis.cookbook.api import backend_for, backend_for_action  # noqa: F401
