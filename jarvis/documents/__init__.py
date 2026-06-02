"""Documents — markdown long-form with version history + AI co-write (personal-OS user documents).

The `documents` table is the source of truth. AI co-write (`documents.ai.propose_edit`) returns a
*proposal*; the operator accepts → a normal `document.update` (a version snapshot). The model never
writes the table directly — Hard Rule #1's spirit holds even though saves are auto-run.
"""
