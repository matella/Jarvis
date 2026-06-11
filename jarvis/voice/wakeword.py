"""OpenWakeWord detector — "Hey Jarvis", local CPU, fed by the gateway's continuous-listen socket.

openwakeword ships a pretrained `hey_jarvis` model (no training needed). The detector is a lazy
singleton; `available()` lets the gateway refuse continuous-listen gracefully when the lib/model
isn't present. Frames are 16 kHz mono PCM16. Privacy: detection runs on-box; nothing is buffered
before a wake (see voice/wake.WakeGate).
"""

from __future__ import annotations

import threading

import numpy as np

from jarvis.config import get_settings

_model = None
_lock = threading.Lock()


def available() -> bool:
    if not get_settings().wake_word_enabled:
        return False
    try:
        import openwakeword  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            from openwakeword.model import Model

            _model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    return _model


def detect(frame_pcm16: bytes, *, threshold: float = 0.5) -> bool:
    """True if the wake word fires in this frame (16 kHz mono PCM16, ≥400 samples)."""
    audio = np.frombuffer(frame_pcm16, dtype=np.int16)
    if audio.size == 0:
        return False
    scores = _get_model().predict(audio)
    return any(v >= threshold for v in scores.values())


def reset() -> None:
    """Clear detector state between utterances (it keeps an internal audio buffer)."""
    if _model is not None:
        _model.reset()


def rms_is_speech(frame_pcm16: bytes, *, threshold: int = 500) -> bool:
    """Cheap VAD: RMS energy over the frame (PCM16). Good enough to find trailing silence."""
    audio = np.frombuffer(frame_pcm16, dtype=np.int16)
    if audio.size == 0:
        return False
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64))))) >= threshold
