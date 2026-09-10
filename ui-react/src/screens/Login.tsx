import { useState } from "react";

import { api } from "../lib/api";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!pw || busy) return;
    setBusy(true);
    setErr("");
    try {
      await api.login(pw);
      onSuccess();
    } catch {
      setErr("Wrong password — try again");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-6">
      <div className="w-full max-w-[340px] flex flex-col items-center">
        <div className="w-20 h-20 rounded-[28px] bg-gradient-to-br from-accent-magenta via-accent to-accent-cyan flex items-center justify-center text-white text-[34px] font-black shadow-lift">A</div>
        <h1 className="text-[38px] font-black tracking-tight mt-5 arc-gradient-text">ARC</h1>
        <p className="text-[14.5px] text-ink-dim mt-1">Your autonomous agent. Unrestricted. Always on.</p>
        <input
          type="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Operator password"
          className="w-full rounded-2xl border border-line bg-surface px-4 py-3.5 mt-8 outline-none focus:ring-2 focus:ring-accent/30 text-ink placeholder:text-ink-dim"
        />
        <button
          onClick={submit}
          disabled={!pw || busy}
          className="w-full bg-accent text-white rounded-2xl py-3.5 font-semibold mt-3 shadow-soft disabled:opacity-50 active:scale-[0.99] transition-all"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-[13px] text-red-500 mt-3 min-h-[18px]">{err}</p>
      </div>
    </div>
  );
}
