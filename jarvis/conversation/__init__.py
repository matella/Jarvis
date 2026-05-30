"""Conversation surface (6a) — session/turn store + the memory window for context assembly.

The chat is a client over existing capabilities, not a new brain. This package owns the
`conversations`/`messages` read model (migration 0011); the executive reasoning lives in
`jarvis/agents/conversation.py` and the transport in `jarvis/gateway/`.
"""
