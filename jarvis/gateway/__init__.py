"""Gateway (6a) — FastAPI + WebSocket transport for the conversational surface.

The first real auth surface: a bearer token resolves to an `actor` (+ capability scopes) that flows
into the 5.5b audit log. The gateway is transport only — reasoning lives in
`jarvis/agents/conversation.py`, capabilities behind the existing M4 gate. Local homelab only.
"""
