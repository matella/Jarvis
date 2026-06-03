"""Generic presenter — turn ANY data (any tool/agent/connector output) into a renderable artifact.

Two pieces, both honoring the Hard Rules (deterministic boundary; one-shot; read-only rendering):

- `auto_artifact(title, data)` — wrap arbitrary data as a `kind="auto"` artifact; the frontend's
  universal AutoView renders it (lists→tables, records→key/value, numbers→stats, nested→sections).
  Zero inference. Any code can present its output with one line.
- `present(data, request, ...)` — ONE inference (the "presenter agent"): given the data + what the
  user asked, choose the format (structured `auto` vs prose `markdown`) + a good title. Falls back
  to `auto_artifact` on any failure, so it never blocks.
"""

from jarvis.present.presenter import auto_artifact, present  # noqa: F401
