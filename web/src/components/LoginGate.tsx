// Login gate. Probes a protected endpoint on mount: 200 → render the app (open dev mode just works);
// 401 → show the passphrase login. On success the session token is stored (it doubles as the bearer)
// and we re-probe. The whole app renders inside this gate.

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../lib/api";

type Phase = "checking" | "login" | "ready";

export function LoginGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const probe = useCallback(async () => {
    try {
      await api.facts.list(); // any protected route; 200 in open mode or with a valid session
      setPhase("ready");
    } catch (e) {
      setPhase(e instanceof ApiError && e.status === 401 ? "login" : "ready");
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(passphrase);
      setPassphrase("");
      await probe();
    } catch {
      setError("Incorrect passphrase.");
    } finally {
      setBusy(false);
    }
  };

  if (phase === "checking") {
    return (
      <div className="flex h-full items-center justify-center bg-void">
        <span className="label animate-pulse">connecting…</span>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <div className="atmosphere grain flex h-full items-center justify-center bg-void p-6">
        <form onSubmit={submit} className="w-full max-w-sm border border-edge bg-panel/40 p-6">
          <div className="mb-1 font-display text-lg font-700 tracking-[0.3em] text-ink">JARVIS</div>
          <div className="label mb-5">sign in</div>
          <input
            type="password"
            autoFocus
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="passphrase"
            className="w-full border border-edge bg-void px-3 py-2 text-ink outline-none focus:border-teal"
          />
          {error && <div className="mt-2 text-sm text-[#ff7a45]">{error}</div>}
          <button
            type="submit"
            disabled={busy || !passphrase}
            className="mt-4 w-full border border-teal/40 bg-teal/15 py-2 text-sm uppercase tracking-widest text-teal transition hover:bg-teal/25 disabled:opacity-40"
          >
            {busy ? "…" : "enter"}
          </button>
        </form>
      </div>
    );
  }

  return <>{children}</>; // logged in, or open dev mode
}
