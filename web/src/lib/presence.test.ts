import { describe, expect, it } from "vitest";

import { isPresenceState, orbVisual, PRESENCE_STATES } from "./presence";

describe("orb presence state machine", () => {
  it("maps every presence state to a distinct, complete visual", () => {
    const captions = new Set<string>();
    for (const state of PRESENCE_STATES) {
      const v = orbVisual(state);
      expect(v.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(v.accent).toMatch(/^#[0-9a-f]{6}$/i);
      expect(v.turbulence).toBeGreaterThanOrEqual(0);
      expect(v.intensity).toBeGreaterThan(0);
      expect(v.caption.length).toBeGreaterThan(0);
      captions.add(v.caption);
    }
    expect(captions.size).toBe(PRESENCE_STATES.length); // no two states look the same
  });

  it("only speaking and alert emit sonar rings", () => {
    expect(orbVisual("speaking").rings).toBe(true);
    expect(orbVisual("alert").rings).toBe(true);
    expect(orbVisual("idle").rings).toBe(false);
    expect(orbVisual("thinking").rings).toBe(false);
    expect(orbVisual("frozen").rings).toBe(false);
  });

  it("thinking is the most agitated, frozen the calmest", () => {
    const t = orbVisual("thinking");
    const f = orbVisual("frozen");
    expect(t.speed).toBeGreaterThan(orbVisual("idle").speed);
    expect(f.speed).toBeLessThan(orbVisual("idle").speed);
    expect(f.turbulence).toBeLessThan(t.turbulence);
  });

  it("falls back to idle on an unknown state", () => {
    expect(orbVisual("bogus" as never).caption).toBe(orbVisual("idle").caption);
  });

  it("validates presence strings from the wire", () => {
    expect(isPresenceState("speaking")).toBe(true);
    expect(isPresenceState("dancing")).toBe(false);
  });
});
