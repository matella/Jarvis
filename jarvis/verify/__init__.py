"""Outcome verification (backlog #1) — close the loop: did the action actually work?

After an execution settles, a DETERMINISTIC check (no LLM) asks whether the intended effect held —
the target container is running and no fresh failures followed. The verdict is a queryable row + a
`verification.completed` event. This is the substrate trustworthy autonomy needs: confidence,
learning, and auto-postmortems all key off whether past actions actually worked.
"""
