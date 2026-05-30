// Spoken replies via the browser's on-device Web Speech synthesis (no server/Piper needed, and no
// audio leaves the machine). While speaking we pulse the shared audioLevel so the orb blooms with
// the voice. Toggle persisted in localStorage; respects reduced-motion by simply not pulsing.

import { setAudioLevel } from "./audioLevel";

const KEY = "jarvis.speak";

export function speakEnabled(): boolean {
  return localStorage.getItem(KEY) !== "off"; // default ON
}

export function setSpeakEnabled(on: boolean): void {
  localStorage.setItem(KEY, on ? "on" : "off");
  if (!on) cancel();
}

export function available(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function cancel(): void {
  if (available()) window.speechSynthesis.cancel();
  setAudioLevel(0);
}

// Mobile webviews only allow speech AFTER it's been unlocked inside a user gesture. Replies arrive
// over the WebSocket (not a gesture), so we prime synthesis once on the first user action (send/
// tap) by speaking a silent utterance — then later speak() calls from message handlers work.
let primed = false;

export function primeSpeech(): void {
  if (primed || !available()) return;
  primed = true;
  try {
    window.speechSynthesis.getVoices(); // nudge async voice loading
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
  } catch {
    /* best-effort unlock */
  }
}

let pulseRaf: number | null = null;

function startPulse(): void {
  let t = 0;
  const tick = () => {
    t += 0.12;
    // a gentle, speech-like amplitude so the orb feels alive while talking
    setAudioLevel(0.35 + 0.25 * Math.abs(Math.sin(t * 6)) + 0.15 * Math.abs(Math.sin(t * 13)));
    pulseRaf = requestAnimationFrame(tick);
  };
  tick();
}

function stopPulse(): void {
  if (pulseRaf != null) cancelAnimationFrame(pulseRaf);
  pulseRaf = null;
  setAudioLevel(0);
}

export function speak(text: string): void {
  if (!available() || !speakEnabled() || !text.trim()) return;
  window.speechSynthesis.cancel(); // interrupt any prior utterance
  window.speechSynthesis.resume(); // Android can leave synthesis paused; nudge it
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.0;
  u.pitch = 1.0;
  u.onstart = startPulse;
  u.onend = stopPulse;
  u.onerror = stopPulse;
  window.speechSynthesis.speak(u);
}
