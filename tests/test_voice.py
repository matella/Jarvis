"""10 unit: STT availability gating, TTS command, and the wake-word gate (no pre-wake buffering)."""

from __future__ import annotations

from jarvis.voice import stt, tts
from jarvis.voice.wake import WakeGate


def test_stt_unavailable_without_model(monkeypatch) -> None:
    class S:
        whisper_model = ""  # empty → STT off regardless of the lib
    monkeypatch.setattr(stt, "get_settings", lambda: S())
    assert stt.available() is False


def test_tts_command(monkeypatch) -> None:
    class S:
        piper_bin = "piper"
        piper_voice = "/v/en.onnx"
    monkeypatch.setattr(tts, "get_settings", lambda: S())
    cmd = tts._build_command("/tmp/o.wav")
    assert cmd[0] == "piper" and "/v/en.onnx" in cmd and "/tmp/o.wav" in cmd


def test_tts_unavailable_without_voice(monkeypatch) -> None:
    class Off:
        piper_voice = ""
    monkeypatch.setattr(tts, "get_settings", lambda: Off())
    assert tts.available() is False


def test_wake_gate_does_not_buffer_before_wake() -> None:
    gate = WakeGate(silence_ms=300)
    # frames arriving before a wake word are ignored entirely (privacy guarantee)
    assert gate.feed(b"x", is_speech=True, frame_ms=100) is False
    assert gate.take() == b""


def test_wake_gate_buffers_then_completes_on_silence() -> None:
    gate = WakeGate(silence_ms=300)
    gate.wake()
    assert gate.feed(b"aa", is_speech=True, frame_ms=100) is False  # speech
    assert gate.feed(b"bb", is_speech=False, frame_ms=100) is False  # 100ms silence
    done = gate.feed(b"cc", is_speech=False, frame_ms=200)  # 300ms total silence → complete
    assert done is True
    assert gate.active is False
    assert gate.take() == b"aabbcc"
