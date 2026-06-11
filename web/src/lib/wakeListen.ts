// Continuous listen for "Hey Jarvis" — captures the mic, downsamples to 16 kHz mono PCM16 and
// streams ~128 ms chunks over the conversation WebSocket (kind: wake_chunk). Detection happens
// ON THE BOX (openwakeword); nothing is buffered server-side before the wake word fires.
// Battery/CPU note: this keeps the mic open — it's an explicit toggle, never a default.

let ctx: AudioContext | null = null;
let stream: MediaStream | null = null;
let node: ScriptProcessorNode | null = null;

export function wakeSupported(): boolean {
  return !!navigator.mediaDevices?.getUserMedia;
}

export async function startWakeListen(sendChunk: (b64: string) => void): Promise<void> {
  if (ctx) return; // already listening
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, noiseSuppression: true, echoCancellation: true },
  });
  ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  // 4096 samples per callback; we downsample whatever the context rate is → 16 kHz PCM16.
  node = ctx.createScriptProcessor(4096, 1, 1);
  const inRate = ctx.sampleRate;
  node.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    const ratio = inRate / 16000;
    const outLen = Math.floor(input.length / ratio);
    const pcm = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const v = input[Math.floor(i * ratio)];
      pcm[i] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
    }
    // base64 the bytes (chunk ≈ 2.7 KB — ~8/s)
    let bin = "";
    const bytes = new Uint8Array(pcm.buffer);
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    sendChunk(btoa(bin));
  };
  source.connect(node);
  node.connect(ctx.destination);
}

export function stopWakeListen(): void {
  node?.disconnect();
  node = null;
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  void ctx?.close();
  ctx = null;
}

export function wakeListening(): boolean {
  return ctx !== null;
}
