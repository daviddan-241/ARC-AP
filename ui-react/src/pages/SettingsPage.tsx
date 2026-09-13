import { useEffect, useState } from "react";
import { Bell, ChevronRight, FileQuestion, Globe, Info, KeyRound, Loader2, LockKeyhole, LogOut, Mail, Megaphone, RotateCcw, Trash2, Volume2 } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

type Status = { transport?: string; engine_ready?: boolean; arena_session_status?: { status?: string; detail?: string } };

const VOICE_KEY = "arcReadAloud";
const NOTIFY_KEY = "arcNotifications";

/** Settings — every row is real: live session status, browser notification
 * permission (real Notification API), read-aloud (real speechSynthesis,
 * consumed by ChatPage), the 4-digit PIN (real, hashed server-side),
 * storage usage + reset (real), delete-all-chats (real API loop), issue
 * reporting to the real GitHub repo, and a red log-out that calls the real
 * endpoint. Sections ChatGPT has that this platform has NO backing for
 * (parental controls, trusted contact) are simply not listed — a row that
 * does nothing is a fake row. */
export default function SettingsPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const setAuthed = useStore((s) => s.setAuthed);
  const [status, setStatus] = useState<Status | null>(null);
  const [pin, setPin] = useState("");
  const [pinMsg, setPinMsg] = useState("");
  const [pinBusy, setPinBusy] = useState(false);
  const [readAloud, setReadAloud] = useState(() => localStorage.getItem(VOICE_KEY) === "1");
  const [notify, setNotify] = useState(() => localStorage.getItem(NOTIFY_KEY) === "1" && typeof Notification !== "undefined" && Notification.permission === "granted");
  const [storageKb, setStorageKb] = useState<number | null>(null);
  const [purging, setPurging] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    api.status().then(setStatus).catch(() => null);
    let kb = 0;
    try { kb = JSON.stringify(localStorage).length / 1024; } catch { /* private mode */ }
    setStorageKb(Math.round(kb));
  }, []);

  const toggleReadAloud = () => {
    const next = !readAloud;
    setReadAloud(next);
    localStorage.setItem(VOICE_KEY, next ? "1" : "0");
    if (!next && typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  };

  const toggleNotifications = async () => {
    if (typeof Notification === "undefined") return;
    if (!notify && Notification.permission !== "granted") {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return;
    }
    const next = !notify;
    setNotify(next);
    localStorage.setItem(NOTIFY_KEY, next ? "1" : "0");
  };

  const savePin = async () => {
    if (!/^\d{4}$/.test(pin)) { setPinMsg("Enter a 4-digit PIN."); return; }
    setPinBusy(true); setPinMsg("");
    try {
      const { sha256Hex } = await import("../lib/api");
      await api.putSetting("pin_hash", await sha256Hex(pin));
      const st = await api.settings();
      if ((st as Record<string, string>).pin_hash) { setPinMsg("PIN saved — it unlocks on next cold open."); setPin(""); }
      else setPinMsg("The server didn't store that — try again.");
    } catch { setPinMsg("Failed — try again."); } finally { setPinBusy(false); }
  };

  const purgeChats = async () => {
    setPurging(true); setPurgeMsg("");
    try {
      const list = await api.listConversations();
      await Promise.all(list.map((c) => api.deleteConversation(c.id)));
      setPurgeMsg(`Deleted ${list.length} conversation${list.length === 1 ? "" : "s"} for real.`);
    } catch { setPurgeMsg("Couldn't delete — check your connection and retry."); }
    finally { setPurging(false); }
  };

  const logOut = async () => {
    setLoggingOut(true);
    try { await api.logout(); } catch { /* cookie may already be gone */ }
    setAuthed(false);
  };

  const arena = status?.arena_session_status ?? {};
  const arenaChip = arena.status === "ready" ? "text-emerald-600" : arena.status === "login_required" || arena.status === "captcha_required" ? "text-amber-600" : "text-[#9CA3AF]";

  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <section className="mb-7">
      <h2 className="mb-2 px-1 text-[11px] font-bold uppercase tracking-[.14em] text-[#9CA3AF]">{title}</h2>
      <div className="arc-card overflow-hidden rounded-2xl">{children}</div>
    </section>
  );
  const Row = ({ icon: I, label, sub, right, onClick }: {
    icon: typeof Globe; label: string; sub?: string; right?: React.ReactNode; onClick?: () => void;
  }) => (
    <div onClick={onClick}
      className={`flex items-center gap-3.5 border-b border-[#E5E7EB] p-4 last:border-b-0 ${onClick ? "cursor-pointer hover:bg-black/[.02]" : ""}`}>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-black/[.04] text-[#4B5563]"><I size={16} /></span>
      <span className="min-w-0 flex-1"><b className="block text-[13.5px] text-[#111827]">{label}</b>{sub && <small className="mt-0.5 block text-xs text-[#6B7280]">{sub}</small>}</span>
      {right}
    </div>
  );
  const Toggle = ({ on }: { on: boolean }) => (
    <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${on ? "bg-[#6366F1]" : "bg-[#D1D5DB]"}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[18px]" : "left-0.5"}`} />
    </span>
  );

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-2xl overflow-y-auto px-4 py-8 pb-24 sm:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-[#111827]">Settings</h1>

      <div className="mt-6">
        <Section title="Apps">
          <Row icon={Globe} label="Arena.ai" sub={arena.detail?.slice(0, 90) || "The model session ARC thinks through."}
            onClick={() => openBrowser("https://arena.ai", "arena")}
            right={<span className="flex shrink-0 items-center gap-2"><b className={`text-[11px] font-bold uppercase tracking-wide ${arenaChip}`}>{arena.status ?? "…"}</b><ChevronRight size={15} className="text-[#9CA3AF]" /></span>} />
          <Row icon={Mail} label="Agent email" sub="The agent's own inbox — codes and links get read from here."
            onClick={() => openBrowser("https://mail.google.com", "webmail")}
            right={<ChevronRight size={15} className="text-[#9CA3AF]" />} />
        </Section>

        <Section title="General">
          <Row icon={Bell} label="Notifications" sub={notify ? "On — browser notifications allowed." : typeof Notification === "undefined" ? "Not supported in this browser." : "Off — allow browser notifications."}
            onClick={typeof Notification !== "undefined" ? toggleNotifications : undefined}
            right={<Toggle on={notify} />} />
          <Row icon={Volume2} label="Voice" sub={readAloud ? "On — answers are read aloud after each turn." : "Off — answers stay silent."}
            onClick={toggleReadAloud} right={<Toggle on={readAloud} />} />
        </Section>

        <Section title="Security and login">
          <Row icon={LockKeyhole} label="PIN lock" sub="A 4-digit PIN unlocks the app after your operator password. Stored hashed server-side." />
          <div className="flex items-center gap-2 border-b border-[#E5E7EB] bg-black/[.015] p-4">
            <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))} inputMode="numeric" placeholder="••••"
              className="w-28 rounded-xl border border-[#E5E7EB] bg-white px-3 py-2.5 text-center text-lg font-bold tracking-[.4em] text-[#111827] outline-none focus:border-[#6366F1]/50" />
            <button onClick={savePin} disabled={pinBusy}
              className="flex items-center gap-2 rounded-xl bg-[#6366F1] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-40">
              {pinBusy ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}Save PIN
            </button>
            {pinMsg && <small className="text-xs text-[#6366F1]">{pinMsg}</small>}
          </div>
          <Row icon={LogOut} label="Log out" sub="Ends this session on the server and re-locks the app."
            onClick={logOut}
            right={loggingOut ? <Loader2 size={15} className="animate-spin text-rose-600" /> : <b className="text-[13px] font-semibold text-rose-600">Log out</b>} />
        </Section>

        <Section title="Storage and data">
          <Row icon={RotateCcw} label="Reset local session" sub={`Clears cached state on this device (${storageKb ?? 0} KB). Server data is untouched.`}
            onClick={() => { localStorage.clear(); sessionStorage.clear(); location.reload(); }}
            right={<ChevronRight size={15} className="text-[#9CA3AF]" />} />
          <Row icon={Trash2} label="Delete all chats" sub="Really deletes every conversation from the server — permanent."
            onClick={purging ? undefined : purgeChats}
            right={purging ? <Loader2 size={15} className="animate-spin text-rose-600" /> : <b className="text-[13px] font-semibold text-rose-600">Delete</b>} />
          {purgeMsg && <small className="block bg-black/[.015] p-3 text-xs text-[#6366F1]">{purgeMsg}</small>}
        </Section>

        <Section title="Get help">
          <Row icon={Megaphone} label="Report app issue" sub="Opens a pre-filled issue on the ARC-AP repo."
            onClick={() => { window.open("https://github.com/daviddan-241/ARC-AP/issues/new?title=App%20issue%3A%20", "_blank"); }}
            right={<ChevronRight size={15} className="text-[#9CA3AF]" />} />
          <Row icon={FileQuestion} label="Help center" sub="Readme and docs in the repo."
            onClick={() => { window.open("https://github.com/daviddan-241/ARC-AP", "_blank"); }}
            right={<ChevronRight size={15} className="text-[#9CA3AF]" />} />
          <Row icon={Info} label="About" sub={`ARC — ArenaOS operator layer. Transport: ${status?.transport ?? "…"}. Engine: ${status?.engine_ready ? "ready" : "…"}.`} />
        </Section>
      </div>
    </div>
  );
}
