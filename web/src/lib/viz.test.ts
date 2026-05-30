import { describe, expect, it } from "vitest";

import { layoutTopology, shortName, sparklinePath, thresholdY } from "./viz";

describe("viz geometry", () => {
  it("sparklinePath starts with M and has one point per value", () => {
    const path = sparklinePath([1, 2, 3], 100, 50);
    expect(path.startsWith("M")).toBe(true);
    expect((path.match(/[ML]/g) ?? []).length).toBe(3);
  });

  it("sparklinePath is empty for no data", () => {
    expect(sparklinePath([], 100, 50)).toBe("");
  });

  it("sparklinePath puts the max value near the top (small y)", () => {
    // ascending series → last point (max) should have the smallest y
    const pts = sparklinePath([0, 50, 100], 100, 50)
      .split(" ")
      .map((p) => Number(p.slice(1).split(",")[1]));
    expect(pts[2]).toBeLessThan(pts[0]);
  });

  it("thresholdY sits within the chart box", () => {
    const y = thresholdY(80, [10, 90], 50);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(y).toBeLessThanOrEqual(50);
  });

  it("layoutTopology centers a single node and spreads many", () => {
    expect(layoutTopology(["a"], 200, 200)).toEqual([{ id: "a", x: 100, y: 100 }]);
    const ring = layoutTopology(["a", "b", "c", "d"], 200, 200);
    expect(ring).toHaveLength(4);
    // distinct positions
    expect(new Set(ring.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)).size).toBe(4);
  });

  it("shortName strips the entity prefix", () => {
    expect(shortName("container:jarvis-postgres")).toBe("jarvis-postgres");
    expect(shortName("plain")).toBe("plain");
  });
});
