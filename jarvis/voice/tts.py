"""Text-to-speech — pluggable backend. Text → WAV audio bytes.

`tts_backend` picks the engine: **piper** (local subprocess, audio never leaves the box — the
default) or **elevenlabs** (cloud, premium multilingual voice; the reply TEXT goes off-box, so it's
an explicit opt-in: API key + egress allowlist). Both return WAV bytes, so the gateway/console
contract is identical. `available()` lets the gateway fall back to browser speech when neither is
ready.
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import wave

from jarvis.config import get_settings


class TTSUnavailable(Exception):
    """No configured/runnable TTS backend."""


# ── dispatcher ──

def available() -> bool:
    s = get_settings()
    if s.tts_backend == "elevenlabs":
        return _elevenlabs_ready()
    return bool(s.piper_voice)


def synthesize(text: str) -> bytes:
    """Render `text` to WAV bytes with the configured backend. Raises TTSUnavailable."""
    if get_settings().tts_backend == "elevenlabs":
        return _elevenlabs_synthesize(text)
    return _piper_synthesize(text)


# ── piper (local, default) ──

def _build_command(out_path: str) -> list[str]:
    s = get_settings()
    return [s.piper_bin, "--model", s.piper_voice, "--output_file", out_path]


def _piper_synthesize(text: str) -> bytes:
    s = get_settings()
    if not s.piper_voice:
        raise TTSUnavailable("piper_voice not configured")
    with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
        try:
            subprocess.run(
                _build_command(fh.name), input=text, text=True,
                capture_output=True, timeout=60, check=True,
            )
        except FileNotFoundError as exc:
            raise TTSUnavailable(f"piper binary not found: {s.piper_bin}") from exc
        except subprocess.CalledProcessError as exc:
            raise TTSUnavailable(f"piper failed: {exc.stderr or exc}") from exc
        fh.seek(0)
        return fh.read()


# ── elevenlabs (cloud, opt-in) ──

_EL_HOST = "api.elevenlabs.io"
_EL_RATE = 22050  # matches output_format=pcm_22050


def _elevenlabs_ready() -> bool:
    from jarvis.security.egress import allowed

    return bool(get_settings().elevenlabs_api_key) and allowed(_EL_HOST)


def _pcm_to_wav(pcm: bytes, *, rate: int = _EL_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV container (the console expects WAV)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _elevenlabs_synthesize(text: str) -> bytes:
    from jarvis.security.egress import guarded_request

    s = get_settings()
    if not _elevenlabs_ready():
        raise TTSUnavailable(
            "elevenlabs not enabled — set ELEVENLABS_API_KEY and allowlist api.elevenlabs.io")
    url = (f"https://{_EL_HOST}/v1/text-to-speech/{s.elevenlabs_voice_id}"
           f"?output_format=pcm_{_EL_RATE}")
    body = json.dumps({"text": text, "model_id": s.elevenlabs_model}).encode()
    try:
        resp = guarded_request(url, data=body, timeout=30.0, headers={
            "xi-api-key": s.elevenlabs_api_key, "Content-Type": "application/json"})
        return _pcm_to_wav(resp.read())
    except Exception as exc:  # noqa: BLE001 — surface as the one TTS error type
        raise TTSUnavailable(f"elevenlabs failed: {type(exc).__name__}") from exc
