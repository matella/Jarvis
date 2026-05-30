import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";
import { initNative } from "./lib/native";

initNative(); // status bar / splash / back-button / keyboard on the native shell (no-op on web)

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// PWA: register the offline-shell service worker in production builds only (avoids HMR conflicts).
// Skipped in the native app (Capacitor serves bundled assets; no SW needed).
if (import.meta.env.PROD && !("Capacitor" in window) && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline shell is best-effort */
    });
  });
}
