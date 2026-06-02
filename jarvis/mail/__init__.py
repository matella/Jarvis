"""Mail module — inbox cache + triage + compose draft + search (personal-OS module #7).

Extends the existing `connectors/mail.py` (IMAP read→events, gated `mail.send`). The `mail_cache`
table is a re-syncable MIRROR (not the source of truth). Triage is one one-shot classification per
new message; compose drafts a reply with one inference (operator edits + sends through the gate).
Live IMAP sync wiring needs the IMAP spike (operator credentials) — see the master plan.
"""
