import { defineConfig } from "@playwright/test";

// E2E smoke against the running console. Starts the Vite dev server; the gateway should be up
// separately (jarvis serve) for the data panels, but the shell/orb/palette tests are backend-free.
// First run needs browsers: `npx playwright install chromium`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:5273", headless: true },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5273",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
