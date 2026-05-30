// The orb's visual language — a pure mapping from presence state to render parameters.
// Pure and exhaustively typed so it can be unit-tested without WebGL (see presence.test.ts).

import type { PresenceState } from "./types";

export interface OrbVisual {
  /** Core color (hex). */
  color: string;
  /** Secondary rim/halo color. */
  accent: string;
  /** Surface displacement amplitude — how agitated the sphere looks. */
  turbulence: number;
  /** Breathing/pulse speed multiplier. */
  speed: number;
  /** Emissive intensity (glow). */
  intensity: number;
  /** Whether to emit expanding sonar rings (speaking). */
  rings: boolean;
  /** Human-readable status word shown under the orb. */
  caption: string;
}

const VISUALS: Record<PresenceState, OrbVisual> = {
  idle: {
    color: "#2aa39b", accent: "#3de0d5", turbulence: 0.10, speed: 0.5,
    intensity: 0.85, rings: false, caption: "Standing by",
  },
  listening: {
    color: "#3de0d5", accent: "#7df7ee", turbulence: 0.16, speed: 0.9,
    intensity: 1.15, rings: false, caption: "Listening",
  },
  thinking: {
    color: "#4d8dff", accent: "#9bc0ff", turbulence: 0.42, speed: 2.1,
    intensity: 1.25, rings: false, caption: "Reasoning",
  },
  speaking: {
    color: "#3de0d5", accent: "#5af2e8", turbulence: 0.30, speed: 1.5,
    intensity: 1.5, rings: true, caption: "Speaking",
  },
  alert: {
    color: "#ff7a45", accent: "#ffb454", turbulence: 0.55, speed: 2.6,
    intensity: 1.6, rings: true, caption: "Alert",
  },
  frozen: {
    color: "#5d7280", accent: "#7d93a3", turbulence: 0.04, speed: 0.16,
    intensity: 0.5, rings: false, caption: "Maintenance — frozen",
  },
};

export function orbVisual(state: PresenceState): OrbVisual {
  return VISUALS[state] ?? VISUALS.idle;
}

export const PRESENCE_STATES: PresenceState[] = [
  "idle", "listening", "thinking", "speaking", "alert", "frozen",
];

export function isPresenceState(value: string): value is PresenceState {
  return (PRESENCE_STATES as string[]).includes(value);
}
