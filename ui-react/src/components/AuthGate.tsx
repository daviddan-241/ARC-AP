import { useEffect, useState } from "react";
import { KeyRound, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, sha256Hex } from "../lib/api";
import { useStore } from "../lib/store";
import BrandMark from "./BrandMark";

type Phase = "loading" | "waking" | "password" | "pin" | "ready";

/* Escalating timeouts that bracket a free-host cold start (30-60s): the
 * default 25s request budget fails right in the middle of waking up, which
 * is what made login look like an infinite spinner. 25s → 40s → 90s. */
const BOOT_BUDGETS_MS = [25000, 40000, 90000];

/** Real auth gate for the whole app: operator password → 4-digit PIN.
 * Everything is verified against the live backend — nothing is faked. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const setAuthed = useStore((s) => s.setAuthed);
  const authed = useStore((s) => s.authed);
  const [phase, setPhase] = useState<Phase>("loading");
  const [pinHash, setPinHash] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [offline, setOffline] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  // Boot check with escalating retries through the cold-start window.
  // Never spins forever: after the last budget it lands on the password
  // screen with an honest banner + a manual retry — the user is never stuck.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let i = 0; i < BOOT_BUDGETS_MS.length; i++) {
        if (cancelled) return;
        setAttempt(i + 1);
        try {
          const st = await api.settingsSlow(BOOT_BUDGETS_MS[i]);
          if (cancelled) return;
          setPinHash((st as Record<string, string>).pin_hash || null);
          setOffline(false);
          setPhase("password");
          return;
        } catch {
          if (cancelled) return;
          if (i < BOOT_BUDGETS_MS.length - 1) {
            // timed out mid cold-start — the host is still waking; show that honestly
            setPhase("waking");
            await new Promise((r) => setTimeout(r, 2000));
          } else {
            setOffline(true);
            setPhase("password");
          }
        }
      }
    })();
    return () => { cancelled = true; };
  }, [retryToken]);

  const retryBoot = () => { setOffline(false); setPhase("loading"); setRetryToken((t) => t + 1); };

  // after the operator password verifies, the PIN (if one exists) unlocks the app
  useEffect(() => {
    if (authed && phase !== "ready") setPhase(pinHash ? "pin" : "ready");
  }, [authed, phase, pinHash]);

  // real logout: once `authed` flips back to false (see ProfileSheet's Log
  // out, which calls the real /api/auth/logout first), drop straight back
  // to the password screen. Without this the gate stayed stuck on "ready"
  // with nothing rendered -- authed was false but phase never moved off
  // "ready", so neither branch below matched.
  useEffect(() => {
    if (!authed && phase === "ready") setPhase("password");
  }, [authed, phase]);

  if (phase === "ready" && authed) return <>{children}</>;

  /* v14: STATIC height. The old --app-vh (visualViewport) wiring re-centered
   * this card every time the keyboard opened/closed — the card "left its
   * place", which is exactly what Danny reported. A login screen needs none
   * of that: fixed 100dvh, browser auto-scrolls the focused field into view,
   * the card itself never moves. Simple and normal, like every login page. */
  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-6">
      <div className="arc-card w-full max-w-sm rounded-3xl p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <BrandMark />
          <div>
            <h1 className="arc-title text-2xl font-bold text-[#111827]">ARC<span className="text-[#6366F1]">.</span></h1>
            <p className="mt-1 text-xs text-[#6B7280]">Operator access only</p>
          </div>
        </div>
        {(phase === "loading" || phase === "waking") && (
        <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
          <div className="flex items-center gap-2 text-sm text-[#6B7280]"><Loader2 size={16} className="animate-spin" />{phase === "waking" ? "Host still waking up…" : "Checking session…"}</div>
          <p className="text-[11px] text-[#9CA3AF]">Free hosting cold start can take up to a minute — attempt {attempt}/{BOOT_BUDGETS_MS.length}.</p>
        </div>
      )}
      {phase === "password" && offline && (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-[12px] text-amber-600">
          The server didn't respond (still cold-starting or offline). You can retry the connection or type your password once it's up.
          <button onClick={retryBoot} className="mt-2 block w-full rounded-lg bg-amber-300/20 px-3 py-2 font-medium text-amber-100 active:scale-95">Retry connection</button>
        </div>
      )}
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
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      // Honest errors: a timeout is NOT "wrong password" — say what happened.
      setError(msg.includes("timed out")
        ? "The server didn't answer in time (cold start or offline). Tap Unlock again in a moment — your password wasn't checked yet."
        : "Wrong password — this is the operator password set on the server.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
      <div className="flex items-center gap-2 rounded-xl border border-[#E5E7EB] bg-black/[.04] px-3 py-2.5 focus-within:border-[#6366F1]/50">
        <KeyRound size={15} className="text-[#6B7280]" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus
          placeholder="Operator password" className="flex-1 bg-transparent text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <button type="submit" disabled={busy || !password}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#6366F1] py-2.5 text-sm font-bold text-white disabled:opacity-40 active:scale-[.98]">
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
      <p className="mb-1 flex items-center gap-1.5 text-center text-[11px] text-[#6B7280]"><ShieldCheck size={12} className="mx-auto" />{isNew ? "Create your 4-digit PIN" : "Enter your 4-digit PIN"}</p>
      <input inputMode="numeric" pattern="\d*" maxLength={4} value={pin} autoFocus
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        className="w-full rounded-xl border border-[#E5E7EB] bg-black/[.04] py-3 text-center text-2xl font-bold tracking-[.6em] text-[#111827] outline-none focus:border-[#6366F1]/50" placeholder="••••" />
      {isNew && (
        <input inputMode="numeric" pattern="\d*" maxLength={4} value={confirmPin}
          onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ""))}
          className="w-full rounded-xl border border-[#E5E7EB] bg-black/[.04] py-3 text-center text-2xl font-bold tracking-[.6em] text-[#111827] outline-none focus:border-[#6366F1]/50" placeholder="••••" />
      )}
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <button type="submit" disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#6366F1] py-2.5 text-sm font-bold text-white disabled:opacity-40 active:scale-[.98]">
        {busy ? <Loader2 size={15} className="animate-spin" /> : null}{isNew ? "Set PIN" : "Unlock"}
      </button>
    </form>
  );
}
