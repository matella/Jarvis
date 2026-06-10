# Voice — pluggable TTS (Piper local default, ElevenLabs opt-in)

**Date:** 2026-06-10 · **Status:** approved, building

## Already true (audit)
STT is live: faster-whisper in-process in the gateway image (base.en pre-baked), browser mic +
wake-word machinery exist. Server TTS (Piper) is coded but not installed → browser speechSynthesis
speaks today. Gateway loop: audio in → STT → respond() → TTS out (`_transcribe`/`_speak`).

## Changes
1. **`voice/tts.py` becomes a dispatcher.** `tts_backend ∈ {piper, elevenlabs}` (default piper).
   `available()`/`synthesize()` route to the backend; Piper path unchanged (subprocess).
2. **ElevenLabs backend (opt-in, off-box).** `guarded_request` POST to
   `api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_22050`, body
   `{text, model_id}` (default `eleven_flash_v2_5` — fast, cheap, FR+EN multilingual), header
   `xi-api-key`. PCM → WAV via stdlib `wave`, so the console contract (`{"kind":"tts","wav":…}`)
   is unchanged. Dormant until `ELEVENLABS_API_KEY` set AND `api.elevenlabs.io` egress-allowlisted
   — sending reply text off-box is the operator's explicit choice (capability text says so).
3. **Enable Piper for real.** `piper-tts` (pip) added to the `[voice]` extra; the **French voice**
   `fr_FR-siwis-medium` baked into the image (user speaks FR; Jarvis now mirrors language).
   `PIPER_VOICE` set in compose. Known limitation: one Piper voice = one language (EN replies get a
   French accent) — the ElevenLabs opt-in is the fix when it matters.
4. **Capability entry** "voice" with accurate backend status + remedies.

## Config
`tts_backend="piper"` · `elevenlabs_api_key=""` · `elevenlabs_voice_id="21m00Tcm4TlvDq8ikWAM"` ·
`elevenlabs_model="eleven_flash_v2_5"` (existing: piper_bin/piper_voice/whisper_*).

## Verification
Unit: dispatcher routing, PCM→WAV wrapping, dormant logic. Live: in-container
`tts.synthesize("Bonjour…")` returns a RIFF WAV; STT still `available()`; console speaks on next use.

## Out of scope
Wake-word enablement, per-language Piper voice switching, cloud STT (never — stays local).
