"""Voice (Phase 10) — local/CPU transport over the conversation pipeline.

Voice adds NO reasoning: mic audio → STT → the same `conversation.respond` path → TTS audio out.
Whisper.cpp (STT), Piper (TTS), OpenWakeWord (wake) are external binaries; these wrappers are thin
and degrade gracefully when a binary/model isn't configured. The orb's audio-reactivity lives in
the frontend (6b). Actions reached via voice are still gated + audited like any other turn.
"""
