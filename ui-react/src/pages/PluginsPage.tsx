import { useEffect, useState } from "react";
import { CheckCircle2, Globe, Loader2, Mail, PlugZap } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import PageHeader from "../components/PageHeader";

type Conn = {
  id: string; name: string; detail: string; connected: boolean;
  act: () => void;
};

/** Real connections only: the arena.ai model session and the agent's own email,
 * both real logins done through the live in-app browser. No fake Gmail/GitHub
 * cards — if a connector isn't actually wired, it doesn't appear. */
export default function PluginsPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const [arenaStatus, setArenaStatus] = useState<string>("");
  const [arenaDetail, setArenaDetail] = useState<string>("");
  const [vaultEmail, setVaultEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const st = await api.status();
        const a = st.arena_session_status ?? {};
        setArenaStatus(a.status ?? "unknown");
        setArenaDetail(a.detail ?? "");
      } catch { /* gate handles auth */ }
      try {
        const items = await api.vault();
        const email = items.find((i) => i.name === "arena_web_email");
        setVaultEmail(email ? "connected" : null);
      } catch { /* vault empty is fine */ }
      setLoading(false);
    })();
  }, []);

  const conns: Conn[] = [
    {
      id: "arena", name: "arena.ai", connected: ["ready", "api_mode"].includes(arenaStatus),
      detail: arenaStatus === "ready" ? "Model transport live — the agent is thinking through this session."
        : arenaStatus === "login_required" ? "Needs your sign-in once. Open the browser and log in — cookies stick."
        : arenaStatus === "captcha_required" ? "A captcha blocked auto-login. Open the browser and solve it once."
        : arenaStatus === "api_mode" ? "Running in API mode (formal endpoint)."
        : `Status: ${arenaStatus || "checking…"}${arenaDetail ? ` — ${arenaDetail.slice(0, 120)}` : ""}`,
      act: () => openBrowser("https://arena.ai", "arena"),
    },
    {
      id: "email", name: "Agent email", connected: vaultEmail === "connected",
      detail: vaultEmail === "connected"
        ? "The agent's inbox is set — it can read mail, tap links, and auto-complete sign-in codes."
        : "Sign the agent into its own webmail once. It reads codes and links from this inbox.",
      act: () => openBrowser("https://mail.google.com", "webmail"),
    },
    {
      id: "browser", name: "Any website", connected: true,
      detail: "The full live browser — log into Discord, banking, anything. Cookies persist server-side.",
      act: () => openBrowser("https://www.google.com", "free"),
    },
  ];

  return (
    <div className="mx-auto min-h-full max-w-5xl px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Connections / 06" title="Connections" description="Everything ARC is actually connected to. Sign-ins happen in the live browser — you type the credentials, the server keeps the session." />
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" />Checking live status…</div>
      ) : (
        <div className="arc-card overflow-hidden rounded-3xl">
          {conns.map((c) => (
            <div key={c.id} className="flex flex-col gap-3 border-b border-white/[.07] p-4 last:border-b-0 sm:flex-row sm:items-center sm:gap-4 sm:p-5">
              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-xs font-bold ${c.connected ? "bg-cyan-300/15 text-cyan-200" : "bg-white/[.06] text-slate-300"}`}>
                {c.id === "arena" ? <Globe size={17} /> : c.id === "email" ? <Mail size={17} /> : <PlugZap size={17} />}
              </span>
              <span className="min-w-0 flex-1">
                <b className="block text-sm text-white">{c.name}</b>
                <small className="mt-1 block text-xs leading-5 text-slate-500">{c.detail}</small>
              </span>
              <div className="flex items-center gap-3">
                {c.connected && <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-300"><CheckCircle2 size={14} />Live</span>}
                <button onClick={c.act} className="flex items-center gap-2 rounded-xl border border-white/[.1] px-3 py-2 text-xs font-semibold text-slate-300 hover:border-cyan-300/30 hover:text-cyan-200">
                  {c.id === "arena" ? "Open sign-in" : c.id === "email" ? "Open mail" : "Open browser"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-4 text-xs leading-5 text-slate-600">No third-party plugin marketplace is wired here yet — these cards show the real, working connections. More connectors can be added the same honest way.</p>
    </div>
  );
}
