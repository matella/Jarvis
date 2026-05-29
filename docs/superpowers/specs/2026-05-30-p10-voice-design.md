# Phase 10 — Voice (+ orb audio-reactivity) — detailed spec

> Date: 2026-05-30 · Voice as transport over the conversation pipeline (all local/CPU), and the orb
> finally comes alive (sound-wave bloom reacting to Jarvis's actual voice).

## Decisions
- **STT:** Whisper.cpp (local). **TTS:** Piper (local). **Wake word:** OpenWakeWord ("Hey Jarvis").
  All CPU, all local-first (CLAUDE.md stack). Voice adds no reasoning — it's transport over 6a.

## Components
- **`voice/stt.py`** — Whisper.cpp wrapper: audio chunk → text (streamed/partial where possible).
- **`voice/tts.py`** — Piper wrapper: text → audio stream (configurable voice).
- **`voice/wake.py`** — OpenWakeWord listener → activates presence (glanceable, not always-recording;
  only buffers after wake).
- **gateway:** WS audio channels — mic audio in → STT → the same `conversation.respond` path; TTS
  audio out streamed to the client; presence-state flips listening→thinking→speaking accordingly.
- **frontend (6b):** mic capture + audio playback; the **orb's `AnalyserNode`** visualizes the TTS
  stream (amplitude/frequency → sound waves) while speaking, and mic input while listening.
- **config:** model paths/voices; wake-word on/off.

## Testing → acceptance
- **Unit:** STT/TTS wrappers (mocked binaries) — text↔audio plumbing; wake-word gate (no buffering
  before wake).
- **Integration:** a recorded WAV → STT text → conversation answer → TTS audio out.
- **Live:** "Hey Jarvis, what's wrong with my media stack?" → orb listens → thinks → speaks with the
  waveform reacting to its voice; actions still gated + audited.

## Dependencies
6a (conversation pipeline + gateway WS), 6b (orb + audio). Whisper.cpp/Piper/OpenWakeWord binaries
on the host.
