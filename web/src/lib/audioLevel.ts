// A shared, mutable audio level (0..1) written by the voice hook and read inside the orb's render
// loop. Kept outside React so it updates at audio framerate without triggering re-renders.

export const audioLevel = { value: 0 };

export function setAudioLevel(v: number): void {
  audioLevel.value = Math.max(0, Math.min(1, v));
}
