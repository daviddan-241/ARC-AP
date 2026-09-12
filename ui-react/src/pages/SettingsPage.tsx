import { useEffect, useState } from "react";
import { Globe, KeyRound, Loader2, LockKeyhole, Mail, RotateCcw } from "lucide-react";
import { api, sha256Hex } from "../lib/api";
import { useStore } from "../lib/store";
import PageHeader from "../components/PageHeader";

/** Settings — real state and real actions: the arena.ai session (live status +
 * sign-in workspace), the agent email, the PIN lock, and the platform status. */
export default function SettingsPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const [status, setStatus] = useState<{ transport?: string; engine_ready?: boolean; arena_session_status?: { status?: string; detail?: string } } | null>(null);
  const [pin, setPin] = useState("");
  const [pinMsg, setPinMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.status().then(setStatus).catch(() => null); }, []);

  const savePin = async () => {
    if (!/^\d{4}$/.test(pin)) { setPinMsg("Enter a 4-digit PIN."); return; }
    setBusy(true); setPinMsg("");
    try {
      await api.putSetting("pin_hash", await sha256Hex(pin));
      const st = await api.settings();
      if ((st as Record<string, string>).pin_hash) { setPinMsg("PIN saved — it unlocks on next cold open."); setPin(""); }
      else setPinMsg("The server didn't store that — try again.");
    } catch { setPinMsg("Failed — try again."); } finally { setBusy(false); }
  };

  const arena = status?.arena_session_status ?? {};
  const arenaChip = arena.status === "ready" ? "text-emerald-300" : arena.status === "login_required" || arena.status === "captcha_required" ? "text-amber-300" : "text-slate-400";

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Control room / 07" title="Settings" description="Tune the operator layer and keep the real sessions healthy." />

      <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <section className="space-y-5">
          {/* arena.ai — the model session, with a real sign-in path */}
          <div className="arc-card rounded-3xl p-5 sm:p-6">
            <div className="mb-4 flex items-start gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-300/10 text-cyan-200"><Globe size={18} /></span>
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-white">arena.ai session</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">ARC thinks through this logged-in web session. Sign in once — the server keeps the cookies.</p>
              </div>
              <span className={`text-[11px] font-bold uppercase tracking-wider ${arenaChip}`}>{arena.status ?? "…"}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => openBrowser("https://arena.ai", "arena")}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 px-4 py-2.5 text-xs font-bold text-[#10132f] active:scale-[.98]">
                <Globe size={14} />Open Arena sign-in
              </button>
            </div>
            {arena.detail && <p className="mt-3 text-[11.5px] leading-5 text-slate-600">{String(arena.detail).slice(0, 200)}</p>}
          </div>

          {/* the agent's own email */}
          <div className="arc-card rounded-3xl p-5 sm:p-6">
            <div className="mb-4 flex items-start gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-400/10 text-violet-200"><Mail size={18} /></span>
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-white">Agent email</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">The agent's own inbox — it reads sign-in codes and taps links from here automatically.</p>
              </div>
            </div>
            <button onClick={() => openBrowser("https://mail.google.com", "webmail")}
              className="flex items-center gap-2 rounded-xl border border-white/[.1] px-4 py-2.5 text-xs font-bold text-white hover:bg-white/[.08]">
              <Mail size={14} />Open the agent's mail
            </button>
          </div>

          {/* PIN lock — real, stored server-side */}
          <div className="arc-card rounded-3xl p-5 sm:p-6">
            <div className="mb-4 flex items-start gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-400/10 text-emerald-200"><KeyRound size={18} /></span>
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-white">PIN lock</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">A 4-digit PIN unlocks the app after your operator password. Stored hashed on the server.</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))} inputMode="numeric" placeholder="••••"
                className="w-28 rounded-xl border border-white/[.09] bg-white/[.035] px-3 py-2.5 text-center text-lg font-bold tracking-[.4em] text-white outline-none focus:border-cyan-300/40" />
              <button onClick={savePin} disabled={busy}
                className="flex items-center gap-2 rounded-xl border border-white/[.1] px-4 py-2.5 text-xs font-bold text-white hover:bg-white/[.08] disabled:opacity-40">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <LockKeyhole size={14} />}Save PIN
              </button>
            </div>
            {pinMsg && <p className="mt-2 text-xs text-cyan-300">{pinMsg}</p>}
          </div>
        </section>

        <section className="space-y-5">
          {/* platform status — real backend values */}
          <div className="arc-card rounded-3xl p-5">
            <h2 className="mb-4 text-sm font-semibold text-white">Platform</h2>
            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between"><span className="text-slate-500">Transport</span><b className="text-white">{status?.transport ?? "…"}</b></div>
              <div className="flex justify-between"><span className="text-slate-500">Task engine</span><b className={status?.engine_ready ? "text-emerald-300" : "text-amber-300"}>{status?.engine_ready ? "ready" : "…"}</b></div>
              <div className="flex justify-between"><span className="text-slate-500">Arena session</span><b className="text-white">{arena.status ?? "…"}</b></div>
            </div>
          </div>

          {/* reset local state */}
          <div className="arc-card rounded-3xl p-5">
            <h2 className="mb-4 text-sm font-semibold text-white">Session</h2>
            <button onClick={() => { localStorage.clear(); sessionStorage.clear(); location.reload(); }}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/[.1] py-2.5 text-xs font-bold text-slate-300 hover:bg-white/[.08]">
              <RotateCcw size={14} />Reset local session
            </button>
            <p className="mt-2 text-[11px] leading-4 text-slate-600">Clears cached chat state on this device and re-locks the app. Server data is untouched.</p>
          </div>
        </section>
      </div>
    </div>
  );
}
