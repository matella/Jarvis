// Native (Capacitor) shell wiring — no-ops on the web. Keeps the dark cinematic look in the
// status bar, hides the splash once React mounts, lets the Android back button leave the app
// from the root, and pads for the soft keyboard. All imports are static but guarded by
// Capacitor.isNativePlatform(), so the web bundle never touches native APIs.

import { App } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { SplashScreen } from "@capacitor/splash-screen";
import { StatusBar, Style } from "@capacitor/status-bar";

export function initNative(): void {
  if (!Capacitor.isNativePlatform()) return;

  // Tag the root so CSS can reserve real clearance for the status bar + gesture/nav bar — the
  // Android WebView is edge-to-edge (Android 15) and often reports env(safe-area-inset-*) as 0.
  document.documentElement.classList.add("cap-native");

  StatusBar.setStyle({ style: Style.Dark }).catch(() => {});
  StatusBar.setBackgroundColor({ color: "#04060a" }).catch(() => {});
  SplashScreen.hide().catch(() => {});

  // The soft keyboard is handled by Capacitor's default WebView resize — no manual padding needed
  // (adding it caused a double-counted gap above the composer).

  // Android hardware back: go back in history, or exit the app at the root.
  App.addListener("backButton", ({ canGoBack }) => {
    if (canGoBack) window.history.back();
    else App.exitApp();
  });
}
