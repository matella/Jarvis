// Voice in the browser: mic capture (→ analyser → orb level, + recorded audio to send) and TTS
// playback (→ analyser → orb level). The orb's audio-reactivity is driven entirely from here via
// the shared `audioLevel`. Recording uses MediaRecorder; the blob is handed to the caller to send
// over /ws as a base64 audio message.

import { useCallback, useRef, useState } from "react";

import { setAudioLevel } from "./audioLevel";

function rms(data: Uint8Array): number {
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

export function micSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window !== "undefined" &&
    window.isSecureContext
  );
}

export function useVoice(onClip: (base64: string) => void) {
  const [recording, setRecording] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const _ctx = () => (ctxRef.current ??= new AudioContext());

  const _pump = useCallback((analyser: AnalyserNode) => {
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      setAudioLevel(Math.min(1, rms(buf) * 3));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, []);

  const _stopPump = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    setAudioLevel(0);
  }, []);

  const startMic = useCallback(async () => {
    // Browsers only allow the mic on a secure context (HTTPS, or localhost). Over http://<ip> it's
    // blocked — surface that clearly instead of silently failing.
    if (!micSupported()) {
      alert(
        "Microphone needs a secure context. Open the console over your HTTPS domain " +
        "(nginx-proxy-manager) or http://localhost on the box.",
      );
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const ctx = _ctx();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    _pump(analyser);

    const chunks: BlobPart[] = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      const blob = new Blob(chunks, { type: recorder.mimeType });
      const b64 = btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
      onClip(b64);
    };
    recorder.start();
    recorderRef.current = recorder;
    setRecording(true);
  }, [_pump, onClip]);

  const stopMic = useCallback(() => {
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    _stopPump();
    setRecording(false);
  }, [_stopPump]);

  const playTts = useCallback(async (wavBase64: string) => {
    const bytes = Uint8Array.from(atob(wavBase64), (c) => c.charCodeAt(0));
    const ctx = _ctx();
    const audioBuf = await ctx.decodeAudioData(bytes.buffer);
    const src = ctx.createBufferSource();
    src.buffer = audioBuf;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    analyser.connect(ctx.destination);
    _pump(analyser);
    src.onended = _stopPump;
    src.start();
  }, [_pump, _stopPump]);

  return { recording, startMic, stopMic, playTts };
}
