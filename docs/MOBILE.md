# Jarvis mobile app (Capacitor)

The Android app is the **same React console** (`web/`) wrapped in a native shell by
[Capacitor](https://capacitorjs.com) — one codebase, the WebGL orb intact, plus a real
home-screen app with native status bar / splash / back-button / keyboard handling. It is **not**
a parallel native rewrite, and notifications stay on **ntfy** (self-hosted, local-first) — see
`.env.example`.

## How it talks to the gateway
The bundled app's origin is `https://localhost` (Capacitor `androidScheme: https`), so it calls the
gateway **cross-origin**. Two things make that work:
- The gateway sets **CORS** to allow the app origin (`GATEWAY_CORS_ORIGINS`, defaulting to the
  capacitor/localhost origins). Add your console's https domain there if you serve it elsewhere.
- The app's **gateway URL is set at runtime** in the ⚙ Connection screen (or `VITE_GATEWAY_URL` at
  build time): point it at your gateway over Tailscale/NPM, e.g. `https://jarvis.<tailnet>.ts.net`.
  Enter the bearer token there too if `GATEWAY_TOKEN` is set. The mic needs a secure context, which
  `https://localhost` provides.

## Build it (on a machine with Android Studio + JDK 17)
Prereqs: Node, Android Studio (SDK + platform-tools), JDK 17. The `web/android/` Gradle project is
committed; build outputs are gitignored.

```bash
cd web
npm install
npm run cap:sync      # = build the SPA + copy it into the android project
npm run cap:open      # opens Android Studio → Run on a device/emulator, or Build > APK/AAB
# or, with a device attached + adb on PATH:
npm run cap:run
```

First launch: open ⚙ → set the **Gateway URL** (your Tailscale/NPM https address) and **Token** if
required → Save. The app reconnects and you're in.

## Updating after web changes
Any change under `web/src` just needs a re-sync:
```bash
npm run cap:sync && npm run cap:open   # then re-run from Android Studio
```

## Notes
- Notifications: install the **ntfy** app and subscribe to your topic (instant delivery). The Jarvis
  app is the control surface; ntfy is the push layer. (A future option is in-app push via Capacitor
  Push Notifications, but that relays through FCM — not local-first — so we keep ntfy.)
- iOS: `npx cap add ios` would work the same way (needs a Mac + Xcode); not set up here.
- Wear OS: notifications mirror from the phone automatically — no separate watch build.
