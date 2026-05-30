import { expect, test } from "@playwright/test";

// Backend-free smoke: the shell mounts, the orb renders, surfaces toggle, and Cmd-K opens.
// (Data panels need `jarvis serve`; this verifies the app skeleton + the new 6b polish wiring.)

test("console shell, orb, surfaces, and command palette", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/JARVIS/);
  await expect(page.locator("canvas")).toBeVisible(); // the presence orb (WebGL)

  // surface toggles
  await page.getByRole("button", { name: "console", exact: true }).click();
  await expect(page.getByText("Intent ledger")).toBeVisible();
  await page.getByRole("button", { name: "insight", exact: true }).click();
  await expect(page.getByRole("button", { name: "Topology" })).toBeVisible();

  // metrics tab
  await page.getByRole("button", { name: "Metrics" }).click();
  await expect(page.getByText(/CPU %/)).toBeVisible();

  // Cmd-K command palette
  await page.keyboard.press("Control+k");
  await expect(page.getByPlaceholder("Type a command…")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Type a command…")).toBeHidden();
});

test("full propose → approve loop is reachable from chat (requires gateway)", async ({ page }) => {
  // Tagged for when the gateway is up; skipped headless-only runs without a backend.
  test.skip(!process.env.JARVIS_E2E_BACKEND, "set JARVIS_E2E_BACKEND=1 with `jarvis serve` running");
  await page.goto("/");
  await page.getByPlaceholder("Speak to Jarvis").fill("restart the nginx container");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/PROPOSAL/)).toBeVisible({ timeout: 25_000 });
  await page.getByRole("button", { name: /Confirm/ }).click();
  await expect(page.getByText(/EXECUTED/)).toBeVisible({ timeout: 25_000 });
});
