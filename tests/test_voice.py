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
        tts_backend = "piper"
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


def test_tts_dispatch_elevenlabs(monkeypatch) -> None:
    # Backend switch routes synthesize() to ElevenLabs and wraps PCM in a WAV container.
    from jarvis.voice import tts

    monkeypatch.setattr(tts, "get_settings", lambda: type("S", (), {
        "tts_backend": "elevenlabs", "elevenlabs_api_key": "k",
        "elevenlabs_voice_id": "v1", "elevenlabs_model": "m1", "piper_voice": ""})())
    monkeypatch.setattr("jarvis.security.egress.allowed", lambda h: True)
    seen = {}

    class _Resp:
        @staticmethod
        def read():
            return b"\x00\x01" * 100  # raw 16-bit PCM

    def fake_req(url, *, data=None, timeout=0, headers=None):
        seen["url"], seen["headers"] = url, headers
        return _Resp()

    monkeypatch.setattr("jarvis.security.egress.guarded_request", fake_req)
    wav = tts.synthesize("Bonjour")
    assert wav[:4] == b"RIFF" and b"WAVE" in wav[:16]      # real WAV container
    assert "v1" in seen["url"] and seen["headers"]["xi-api-key"] == "k"


def test_tts_elevenlabs_dormant_without_key(monkeypatch) -> None:
    from jarvis.voice import tts

    monkeypatch.setattr(tts, "get_settings", lambda: type("S", (), {
        "tts_backend": "elevenlabs", "elevenlabs_api_key": "", "piper_voice": "x.onnx"})())
    assert tts.available() is False     # elevenlabs selected but no key → not available


def test_tts_piper_default_available(monkeypatch) -> None:
    from jarvis.voice import tts

    monkeypatch.setattr(tts, "get_settings", lambda: type("S", (), {
        "tts_backend": "piper", "piper_voice": "/voices/fr.onnx"})())
    assert tts.available() is True
