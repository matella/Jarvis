// Connection settings — set the gateway URL + token at runtime. Essential for the native
// (Capacitor) app, where there's no dev proxy: you point it at your gateway (Tailscale/NPM)
// once and it's stored locally. On the web console both fields are usually left blank
// (same-origin + open dev-mode). Saving reloads so the socket reconnects with the new config.

import { useState } from "react";

import { getGatewayUrl, getToken, setGatewayUrl, setToken } from "../lib/api";

export function ConnectionSettings({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState(getGatewayUrl());
  const [token, setTok] = useState(getToken());

  const save = () => {
    setGatewayUrl(url);
    setToken(token);
    location.reload(); // simplest reliable way to rebuild the WS/REST clients with new config
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md border border-edge bg-void p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 font-display text-sm uppercase tracking-[0.25em] text-ink">
          Connection
        </div>

        <label className="label mb-1 block">Gateway URL</label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://jarvis.your-domain  (the URL you open the web console at)"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          className="mb-1 w-full border border-edge bg-black/40 px-3 py-2 text-sm text-ink outline-none focus:border-teal"
        />
        <p className="mb-4 text-[11px] leading-relaxed text-steel">
          Use the same HTTPS domain that serves the web console (it proxies /ws + /api to the
          gateway). Must be https, and the proxy needs WebSocket support enabled. Blank = same
          origin (web console only).
        </p>

        <label className="label mb-1 block">Token (optional)</label>
        <input
          value={token}
          onChange={(e) => setTok(e.target.value)}
          type="password"
          placeholder="bearer token, if the gateway requires one"
          className="mb-5 w-full border border-edge bg-black/40 px-3 py-2 text-sm text-ink outline-none focus:border-teal"
        />

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="border border-edge px-4 py-2 text-[11px] uppercase tracking-widest text-steel hover:text-ink"
          >
            Cancel
          </button>
          <button
            onClick={save}
            className="border border-teal/50 bg-teal/15 px-4 py-2 text-[11px] uppercase tracking-widest text-teal hover:bg-teal/25"
          >
            Save &amp; reconnect
          </button>
        </div>
      </div>
    </div>
  );
}
