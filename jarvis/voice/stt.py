"""Speech-to-text — local, on-device, CPU (faster-whisper). Audio bytes → text.

Runs entirely inside the gateway container: no external service, no audio leaves the box
(local-first per CLAUDE.md). faster-whisper bundles CTranslate2 + PyAV, so it transcribes the
browser's webm/opus recording directly — no separate binary or ffmpeg step. The model loads once
(lazy singleton); `available()` lets the gateway degrade when the lib/model isn't present.
"""

from __future__ import annotations

import tempfile
import threading

from jarvis.config import get_settings


class STTUnavailable(Exception):
    """faster-whisper not installed, or the model can't be loaded."""


_model = None
_lock = threading.Lock()


def available() -> bool:
    """True if local STT can run (lib importable + a model configured)."""
    if not get_settings().whisper_model:
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model():
    """Load the WhisperModel once (thread-safe). Raises STTUnavailable if unavailable."""
    global _model
    if _model is not None:
        return _model
    s = get_settings()
    if not s.whisper_model:
        raise STTUnavailable("whisper_model not configured")
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTUnavailable("faster-whisper not installed (pip install .[voice])") from exc
            _model = WhisperModel(
                s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute
            )
    return _model


def transcribe(audio: bytes) -> str:
    """Transcribe recorded audio (wav/webm/opus) → text. Raises STTUnavailable if not ready."""
    model = _get_model()
    with tempfile.NamedTemporaryFile(suffix=".audio") as fh:
        fh.write(audio)
        fh.flush()
        try:
            segments, _info = model.transcribe(fh.name, beam_size=1)
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:  # noqa: BLE001 — decode/inference failure → a clean STT error
            raise STTUnavailable(f"transcription failed: {exc}") from exc
