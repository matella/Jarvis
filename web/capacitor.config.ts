import type { CapacitorConfig } from "@capacitor/cli";

// Capacitor wraps the built SPA (dist/) as a native Android app. The UI is bundled locally;
// only data calls go to the gateway, whose URL is set at runtime in Connection Settings (or
// VITE_GATEWAY_URL at build time). androidScheme=https makes the app origin https://localhost,
// which the gateway's CORS allowlist permits and which lets the mic work (secure context).
const config: CapacitorConfig = {
  appId: "net.jarvis.console",
  appName: "Jarvis",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
  android: {
    backgroundColor: "#04060a",
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 800,
      backgroundColor: "#04060a",
      showSpinner: false,
    },
  },
};

export default config;
