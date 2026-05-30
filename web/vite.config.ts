import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The console talks to the 6a gateway. In dev we proxy /api, /ws and /health to it so the
// browser only ever hits the Vite origin (no CORS, no hardcoded host).
const GATEWAY = process.env.JARVIS_GATEWAY ?? "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      "/api": { target: GATEWAY, changeOrigin: true },
      "/health": { target: GATEWAY, changeOrigin: true },
      "/ws": { target: GATEWAY, ws: true, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Vitest owns src/*.test.*; Playwright owns e2e/*.spec.* (don't let Vitest collect those).
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
