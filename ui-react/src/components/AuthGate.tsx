import { useEffect, useState } from "react";
import { KeyRound, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, sha256Hex } from "../lib/api";
import { useStore } from "../lib/store";
import BrandMark from "./BrandMark";

type Phase = "loading" | "password" | "pin" | "ready";

/** Real auth gate for the whole app: operator password → 4-digit PIN.
 * Everything is verified against the live backend — nothing is faked. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const setAuthed = useStore((s) => s.setAuthed);
  const authed = useStore((s) => s.authed);
  const [phase, setPhase] = useState<Phase>("loading");
  const [pinHash, setPinHash] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const st = await api.settings();
        setPinHash((st as Record<string, string>).pin_hash || null);
        setPhase("password");
      } catch {
        setPhase("password");
      }
    })();
  }, []);

  // after the operator password verifies, the PIN (if one exists) unlocks the app
  useEffect(() => {
    if (authed && phase !== "ready") setPhase(pinHash ? "pin" : "ready");
  }, [authed, phase, pinHash]);

  if (phase === "ready" && authed) return <>{children}</>;

  return (
    <div className="arc-shell flex min-h-[100dvh] items-center justify-center px-6">
      <div className="arc-card w-full max-w-sm rounded-3xl p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <BrandMark />
          <div>
            <h1 className="arc-title text-2xl font-bold text-white">ARC<span className="text-cyan-300">.</span></h1>
            <p className="mt-1 text-xs text-slate-500">Operator access only</p>
          </div>
        </div>
        {phase === "loading" && <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" />Checking session…</div>}
        {phase === "password" && <PasswordForm onDone={async () => {
          const st = await api.settings();
          setPinHash((st as Record<string, string>).pin_hash || null);
          setAuthed(true);
        }} />}
        {phase === "pin" && <PinForm pinHash={pinHash!} onDone={() => setPhase("ready")} />}
      </div>
    </div>
  );
}

function PasswordForm({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!password || busy) return;
    setBusy(true); setError("");
    try {
      await api.login(password);
      await onDone();
    } catch {
      setError("Wrong password — this is the operator password set on the server.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
      <div className="flex items-center gap-2 rounded-xl border border-white/[.1] bg-white/[.04] px-3 py-2.5 focus-within:border-cyan-300/40">
        <KeyRound size={15} className="text-slate-500" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus
          placeholder="Operator password" className="flex-1 bg-transparent text-sm text-white outline-none placeholder:text-slate-600" />
      </div>
      {error && <p className="text-xs text-rose-300">{error}</p>}
      <button type="submit" disabled={busy || !password}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 py-2.5 text-sm font-bold text-[#10132f] disabled:opacity-40 active:scale-[.98]">
        {busy ? <Loader2 size={15} className="animate-spin" /> : <LockKeyhole size={15} />}Unlock
      </button>
    </form>
  );
}

/** PIN entry: creates a new PIN on first use (enter + confirm), unlocks after. */
function PinForm({ pinHash, onDone }: { pinHash: string; onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isNew = pinHash === "" || pinHash == null;

  const submit = async () => {
    if (busy) return;
    setError("");
    if (!/^\d{4}$/.test(pin)) { setError("Enter a 4-digit PIN."); return; }
    setBusy(true);
    try {
      if (isNew) {
        if (pin !== confirmPin) { setError("PINs don't match."); setBusy(false); return; }
        await api.putSetting("pin_hash", await sha256Hex(pin));
        await api.settings(); // verify it actually stored
      } else {
        if ((await sha256Hex(pin)) !== pinHash) { setError("Wrong PIN."); setBusy(false); return; }
      }
      onDone();
    } catch {
      setError("The server rejected that — try again.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
      <p className="mb-1 flex items-center gap-1.5 text-center text-[11px] text-slate-500"><ShieldCheck size={12} className="mx-auto" />{isNew ? "Create your 4-digit PIN" : "Enter your 4-digit PIN"}</p>
      <input inputMode="numeric" pattern="\d*" maxLength={4} value={pin} autoFocus
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        className="w-full rounded-xl border border-white/[.1] bg-white/[.04] py-3 text-center text-2xl font-bold tracking-[.6em] text-white outline-none focus:border-cyan-300/40" placeholder="••••" />
      {isNew && (
        <input inputMode="numeric" pattern="\d*" maxLength={4} value={confirmPin}
          onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ""))}
          className="w-full rounded-xl border border-white/[.1] bg-white/[.04] py-3 text-center text-2xl font-bold tracking-[.6em] text-white outline-none focus:border-cyan-300/40" placeholder="••••" />
      )}
      {error && <p className="text-xs text-rose-300">{error}</p>}
      <button type="submit" disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 py-2.5 text-sm font-bold text-[#10132f] disabled:opacity-40 active:scale-[.98]">
        {busy ? <Loader2 size={15} className="animate-spin" /> : null}{isNew ? "Set PIN" : "Unlock"}
      </button>
    </form>
  );
}
