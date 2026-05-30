import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// The PWA manifest is static config; validate it has the fields needed to be installable.
describe("PWA manifest", () => {
  const manifest = JSON.parse(
    readFileSync(resolve(__dirname, "../../public/manifest.webmanifest"), "utf8"),
  );

  it("declares an installable standalone app", () => {
    expect(manifest.name).toMatch(/Jarvis/);
    expect(manifest.short_name).toBe("Jarvis");
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");
  });

  it("has a theme color and at least one icon", () => {
    expect(manifest.theme_color).toBe("#04060a");
    expect(Array.isArray(manifest.icons) && manifest.icons.length).toBeTruthy();
    expect(manifest.icons[0].src).toBe("/icon.svg");
    expect(manifest.icons[0].purpose).toContain("maskable");
  });
});
