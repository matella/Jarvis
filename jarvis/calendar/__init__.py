"""Calendar — local editable events (truth) + Google/ICS read-mirror (personal-OS module #8).

`source='local'` events are the source of truth (CRUD, graded auto-run). `google`/`ics` events are a
re-syncable mirror (read-only — editing one is refused; "copy to local" instead). No write-back to
Google in v1. Live Google OAuth sync needs the `make google-oauth` token spike (on hold).
"""
