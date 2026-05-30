// Native (Capacitor) shell wiring — no-ops on the web. Keeps the dark cinematic look in the
// status bar, hides the splash once React mounts, lets the Android back button leave the app
// from the root, and pads for the soft keyboard. All imports are static but guarded by
// Capacitor.isNativePlatform(), so the web bundle never touches native APIs.

import { App } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { Keyboard } from "@capacitor/keyboard";
import { SplashScreen } from "@capacitor/splash-screen";
import { StatusBar, Style } from "@capacitor/status-bar";

export function initNative(): void {
  if (!Capacitor.isNativePlatform()) return;

  StatusBar.setStyle({ style: Style.Dark }).catch(() => {});
  StatusBar.setBackgroundColor({ color: "#04060a" }).catch(() => {});
  SplashScreen.hide().catch(() => {});

  // Reflect the soft keyboard height into a CSS var so the composer can sit above it.
  Keyboard.addListener("keyboardWillShow", (info) => {
    document.documentElement.style.setProperty("--kb", `${info.keyboardHeight}px`);
  });
  Keyboard.addListener("keyboardWillHide", () => {
    document.documentElement.style.setProperty("--kb", "0px");
  });

  // Android hardware back: go back in history, or exit the app at the root.
  App.addListener("backButton", ({ canGoBack }) => {
    if (canGoBack) window.history.back();
    else App.exitApp();
  });
}
