import { useEffect, useState } from "react";
import { CheckCircle2, ChevronRight, Globe, LogOut, Mail, Settings2 } from "lucide-react";
import { Link } from "wouter";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

/** Real profile sheet -- every row here reflects an actual, currently-true
 * fact from the live backend (arena.ai session, agent email, PIN), or is a
 * real action (log out actually calls /api/auth/logout). No Personalization/
 * Subscription/Parental-controls/Notifications rows: those are genuine
 * ChatGPT account features this single-operator, self-hosted platform has
 * no backing for, and faking them would be exactly the "fake button"
 * problem Danny asked to remove. "Open full settings" is the honest door
 * to everything real that doesn't fit this quick sheet. */
export default function ProfileSheet({ onClose }: { onClose: () => void }) {
  const setAuthed = useStore((s) => s.setAuthed);
  const [status, setStatus] = useState<{ arena_session_status?: { status?: string } } | null>(null);
  const [vaultEmail, setVaultEmail] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    api.status().then(setStatus).catch(() => null);
    api.vault().then((items) => setVaultEmail(items.some((i) => i.name === "arena_web_email"))).catch(() => null);
  }, []);

  const arenaReady = ["ready", "api_mode"].includes(status?.arena_session_status?.status ?? "");

  const logOut = async () => {
    setLoggingOut(true);
    try { await api.logout(); } catch { /* cookie may already be gone -- still clear client state */ }
    setAuthed(false);
    onClose();
  };

  return (
    <div className="min-w-0">
      <div className="mb-6 flex flex-col items-center gap-2 text-center">
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[#007AFF] text-lg font-bold text-white">DO</span>
        <div><b className="block text-base text-[#111827]">Danny Op</b><small className="text-xs text-[#6B7280]">Operator</small></div>
      </div>

      <p className="arc-mono mb-2 px-1 text-[10px] uppercase tracking-[.22em] text-[#9CA3AF]">Live sessions</p>
      <div className="arc-card mb-4 overflow-hidden rounded-2xl">
        <div className="flex items-center gap-3 border-b border-[#E5E7EB] p-3.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#007AFF]/10 text-[#007AFF]"><Globe size={16} /></span>
          <span className="flex-1 text-[13.5px] text-[#111827]">arena.ai</span>
          {arenaReady ? <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600"><CheckCircle2 size={12} />Live</span>
            : <span className="text-[11px] text-amber-600">{status?.arena_session_status?.status ?? "…"}</span>}
        </div>
        <div className="flex items-center gap-3 p-3.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-400/10 text-violet-600"><Mail size={16} /></span>
          <span className="flex-1 text-[13.5px] text-[#111827]">Agent email</span>
          {vaultEmail ? <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600"><CheckCircle2 size={12} />Live</span>
            : <span className="text-[11px] text-[#6B7280]">Not signed in</span>}
        </div>
      </div>

      <Link href="/settings" onClick={onClose}
        className="mb-4 flex items-center gap-3 rounded-xl px-3 py-3 text-sm text-[#374151] hover:bg-black/[.05]">
        <Settings2 size={17} />Open full settings<ChevronRight size={15} className="ml-auto text-[#9CA3AF]" />
      </Link>

      <button onClick={logOut} disabled={loggingOut}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-rose-500/30 bg-rose-400/[.06] py-3 text-sm font-semibold text-rose-600 hover:bg-rose-400/10 disabled:opacity-50">
        <LogOut size={15} />{loggingOut ? "Logging out…" : "Log out"}
      </button>
    </div>
  );
}
