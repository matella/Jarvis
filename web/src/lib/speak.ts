// Spoken replies — on-device, nothing leaves the machine. On the native app we use the platform
// TTS engine (@capacitor-community/text-to-speech), because the Android System WebView doesn't
// reliably implement Web Speech synthesis; on the web we use window.speechSynthesis. While
// speaking we pulse the shared audioLevel so the orb blooms with the voice. Toggle in localStorage.

import { Capacitor } from "@capacitor/core";
import { TextToSpeech } from "@capacitor-community/text-to-speech";

import { setAudioLevel } from "./audioLevel";

const KEY = "jarvis.speak";
const IS_NATIVE = Capacitor.isNativePlatform();

export function speakEnabled(): boolean {
  return localStorage.getItem(KEY) !== "off"; // default ON
}

export function setSpeakEnabled(on: boolean): void {
  localStorage.setItem(KEY, on ? "on" : "off");
  if (!on) cancel();
}

function webSpeechOk(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function available(): boolean {
  return IS_NATIVE || webSpeechOk();
}

export function cancel(): void {
  if (IS_NATIVE) TextToSpeech.stop().catch(() => {});
  else if (webSpeechOk()) window.speechSynthesis.cancel();
  stopPulse();
}

// Mobile webviews only allow speech AFTER it's been unlocked inside a user gesture. Replies arrive
// over the WebSocket (not a gesture), so we prime synthesis once on the first user action (send/
// tap) by speaking a silent utterance — then later speak() calls from message handlers work.
let primed = false;

export function primeSpeech(): void {
  if (IS_NATIVE || primed || !webSpeechOk()) return; // native TTS needs no gesture unlock
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

  if (IS_NATIVE) {
    // Platform TTS — reliable in the Android WebView where Web Speech isn't.
    TextToSpeech.stop().catch(() => {});
    startPulse();
    TextToSpeech.speak({ text, lang: "en-US", rate: 1.0, pitch: 1.0, category: "playback" })
      .catch(() => {})
      .finally(stopPulse);
    return;
  }

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
