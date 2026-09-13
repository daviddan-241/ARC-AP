import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Globe, KeyRound, Loader2, Lock, Mail, PlugZap, Plus, Rocket, Search, X } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

type InstalledApp = { id: string; name: string; logo?: string; icon?: typeof Globe; connected: boolean; act: () => void };
type PopularApp = {
  id: string; name: string; desc: string; host: string;
  via: "composio" | "appdeploy" | "email" | "browser";
};

/** Real brand logo (clearbit CDN) with an honest letter-badge fallback when
 * the image can't load — never a fake/broken logo box. */
function Logo({ host, name, size = 22 }: { host: string; name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <span style={{ width: size, height: size }}
      className="flex shrink-0 items-center justify-center rounded-lg bg-[#F3F4F6] text-[11px] font-bold text-[#374151]">{name[0]}</span>;
  }
  return <img src={`https://logo.clearbit.com/${host}`} alt={name} width={size} height={size}
    onError={() => setFailed(true)} className="shrink-0 rounded-lg" />;
}

/** Plugins — the single home for ALL tools & connectors, laid out like the
 * ChatGPT plugins screen: search bar, "Installed" row of live tiles, then
 * a "Popular" list. Every row maps to a REAL action: session sign-ins open
 * the live in-app browser, AppDeploy provisions a real free key, Composio
 * rows route through the real gateway (key stored encrypted in the vault).
 * Nothing is decorative — a connector with no backing is not listed. */
export default function PluginsPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [arenaStatus, setArenaStatus] = useState("");
  const [vaultEmail, setVaultEmail] = useState(false);
  const [appdeployKey, setAppdeployKey] = useState(false);
  const [appdeployBusy, setAppdeployBusy] = useState(false);
  const [appdeployMsg, setAppdeployMsg] = useState("");
  const [composioKey, setComposioKey] = useState(false);
  const [keySheet, setKeySheet] = useState<string | null>(null); // "composio" | null
  const [composioValue, setComposioValue] = useState("");
  const [composioBusy, setComposioBusy] = useState(false);
  const [composioMsg, setComposioMsg] = useState("");

  const refresh = async () => {
    try {
      const st = await api.status();
      setArenaStatus(st.arena_session_status?.status ?? "unknown");
      setAppdeployKey(!!st.appdeploy_key);
      setComposioKey(!!st.composio_key);
    } catch { /* AuthGate handles auth failures */ }
    try {
      const items = await api.vault();
      setVaultEmail(items.some((i) => i.name === "arena_web_email"));
    } catch { /* empty vault is fine */ }
    setLoading(false);
  };
  useEffect(() => { refresh(); }, []);

  const provisionAppDeploy = async () => {
    setAppdeployBusy(true); setAppdeployMsg("");
    try {
      const res = await api.provisionAppDeploy();
      setAppdeployMsg(res.detail || "Key provisioned and stored.");
      await refresh();
    } catch (e) {
      setAppdeployMsg(e instanceof Error ? e.message : "Provisioning failed — try again.");
    } finally { setAppdeployBusy(false); }
  };

  const saveComposio = async () => {
    if (!composioValue.trim()) return;
    setComposioBusy(true); setComposioMsg("");
    try {
      await api.putVault("composio_api_key", "api_key", composioValue.trim());
      setComposioValue("");
      setComposioMsg("Key stored — the agent can now route Gmail, Slack, GitHub and 1,500+ apps through Composio.");
      await refresh();
    } catch (e) {
      setComposioMsg(e instanceof Error ? e.message : "Saving failed.");
    } finally { setComposioBusy(false); }
  };

  // Installed: every tile is a live, verified connection. Tapping a tile
  // runs its real action (sign-in browser, mail, free browser, dashboard).
  const installed: InstalledApp[] = [
    { id: "arena", name: "arena.ai", icon: Globe, connected: ["ready", "api_mode"].includes(arenaStatus),
      act: () => openBrowser("https://arena.ai", "arena") },
    { id: "email", name: "Agent email", icon: Mail, connected: vaultEmail,
      act: () => openBrowser("https://mail.google.com", "webmail") },
    { id: "browser", name: "Browser", icon: Globe, connected: true,
      act: () => openBrowser("https://www.google.com", "free") },
    ...(appdeployKey ? [{ id: "appdeploy", name: "AppDeploy", icon: Rocket, connected: true, act: provisionAppDeploy }] : []),
    ...(composioKey ? [{ id: "composio", name: "Composio", icon: PlugZap, connected: true, act: () => openBrowser("https://dashboard.composio.dev", "free") }] : []),
  ].filter((a) => a.connected);

  // Popular: real apps ARC can genuinely drive today. Gmail / Outlook can
  // also run through the agent's own webmail inbox; the rest route through
  // Composio's real gateway once its key is stored.
  const popular: PopularApp[] = [
    { id: "gmail", name: "Gmail", host: "gmail.com", desc: "Read, draft and send real email through Composio or the agent's own inbox.", via: "composio" },
    { id: "github", name: "GitHub", host: "github.com", desc: "Manage repos, issues and pull requests for ARC's projects.", via: "composio" },
    { id: "drive", name: "Google Drive", host: "drive.google.com", desc: "Read and write files in Drive for research and library work.", via: "composio" },
    { id: "slack", name: "Slack", host: "slack.com", desc: "Send messages and read channels through the Composio gateway.", via: "composio" },
    { id: "outlook", name: "Outlook Email", host: "outlook.com", desc: "Hotmail/Outlook mail for the agent — codes, links, sending.", via: "composio" },
    { id: "notion", name: "Notion", host: "notion.so", desc: "Create and update notes and docs for long-running tasks.", via: "composio" },
    { id: "canva", name: "Canva", host: "canva.com", desc: "Design assets the agent can produce for projects.", via: "composio" },
    { id: "hubspot", name: "HubSpot", host: "hubspot.com", desc: "CRM contacts and deals through the Composio gateway.", via: "composio" },
    { id: "appdeploy", name: "AppDeploy", host: "appdeploy.dev", desc: "Free app hosting — one click provisions a real key, no account needed.", via: "appdeploy" },
    { id: "composio", name: "Composio", host: "composio.dev", desc: "The gateway itself: 1,500+ app tools for the agent.", via: "composio" },
  ];
  const rows: PopularApp[] = popular;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.name.toLowerCase().includes(q) || r.desc.toLowerCase().includes(q));
  }, [query]);

  const rowAction = (r: PopularApp) => {
    if (r.via === "appdeploy") return provisionAppDeploy();
    if (!composioKey) return setKeySheet("composio"); // honest: gateway key needed first
    // real Composio dashboard — where the app's connector is authorized
    openBrowser("https://dashboard.composio.dev", "free");
  };

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-3xl overflow-y-auto px-4 py-8 pb-24 sm:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-[#111827]">Plugins</h1>
      <p className="mt-1 text-sm text-[#6B7280]">The single home for every tool and connector ARC can use. Keys live encrypted server-side.</p>

      {/* search — real client-side filter of the list below */}
      <div className="mt-5 flex items-center gap-2 rounded-full border border-[#E5E7EB] bg-white px-4 py-2.5 shadow-sm focus-within:border-[#007AFF]/50">
        <Search size={16} className="shrink-0 text-[#9CA3AF]" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search plugins"
          className="w-full bg-transparent text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
        {query && <button onClick={() => setQuery("")} aria-label="Clear search" className="text-[#9CA3AF] hover:text-[#111827]"><X size={14} /></button>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-[#6B7280]"><Loader2 size={16} className="animate-spin" />Checking live status…</div>
      ) : (
        <>
          {/* Installed — horizontal row of live tiles */}
          {installed.length > 0 && (
            <section className="mt-7">
              <h2 className="mb-3 text-[13px] font-semibold text-[#111827]">Installed</h2>
              <div className="arc-no-scrollbar flex gap-3 overflow-x-auto pb-1">
                {installed.map((a) => {
                  const I = a.icon!;
                  return (
                    <button key={a.id} onClick={a.act} title={a.name}
                      className="flex w-[86px] shrink-0 flex-col items-center gap-2 rounded-2xl border border-[#E5E7EB] bg-white p-3 shadow-sm active:scale-[.97] hover:border-[#007AFF]/40">
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#007AFF]/10 text-[#007AFF]"><I size={18} /></span>
                      <span className="w-full truncate text-center text-[11.5px] font-medium text-[#374151]">{a.name}</span>
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600"><CheckCircle2 size={10} />Live</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Composio key sheet — opened by any locked row; the ONLY place a
              key is ever pasted. Saves to the encrypted vault for real. */}
          {keySheet === "composio" && (
            <div className="arc-card mt-5 rounded-2xl p-4">
              <div className="mb-2 flex items-center justify-between">
                <b className="flex items-center gap-2 text-sm text-[#111827]"><KeyRound size={14} className="text-[#007AFF]" />Connect Composio first</b>
                <button onClick={() => setKeySheet(null)} aria-label="Close" className="text-[#9CA3AF] hover:text-[#111827]"><X size={15} /></button>
              </div>
              <p className="mb-3 text-xs leading-5 text-[#6B7280]">
                App plugins (Gmail, GitHub, Slack…) run through the Composio gateway. Grab a free API key at
                <button onClick={() => openBrowser("https://dashboard.composio.dev", "free")} className="mx-1 font-semibold text-[#007AFF]">dashboard.composio.dev → API Keys</button>
                and paste it below — it's stored encrypted server-side and
                stays across restarts. (To also survive app redeploys on
                Render's free tier, set <code>COMPOSIO_API_KEY</code> once in
                Render → Environment — ARC re-imports it on every boot.)
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input type="password" value={composioValue} onChange={(e) => setComposioValue(e.target.value)}
                  placeholder="Paste Composio API key…"
                  className="min-w-0 flex-1 rounded-xl border border-[#E5E7EB] px-3.5 py-2.5 text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF] focus:border-[#007AFF]/50" />
                <button onClick={saveComposio} disabled={composioBusy || !composioValue.trim()}
                  className="rounded-xl bg-[#007AFF] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-40">
                  {composioBusy ? "Saving…" : "Save key"}
                </button>
              </div>
              {composioMsg && <small className="mt-2 block text-xs text-[#007AFF]">{composioMsg}</small>}
            </div>
          )}

          {/* Popular — vertical list, logo + name + description + action */}
          <section className="mt-7">
            <h2 className="mb-3 text-[13px] font-semibold text-[#111827]">Popular</h2>
            <div className="arc-card overflow-hidden rounded-2xl">
              {filtered.map((r, i) => {
                const connected = r.via === "appdeploy" ? appdeployKey : r.id === "composio" ? composioKey : false;
                return (
                  <div key={r.id} className={`flex items-center gap-3.5 p-4 ${i > 0 ? "border-t border-[#E5E7EB]" : ""}`}>
                    <Logo host={r.host} name={r.name} />
                    <div className="min-w-0 flex-1">
                      <b className="block text-sm text-[#111827]">{r.name}</b>
                      <small className="block truncate text-xs text-[#6B7280]">{r.desc}</small>
                      {r.via === "appdeploy" && (appdeployBusy || appdeployMsg) && (
                        <small className={`mt-1 block text-[11px] ${appdeployBusy ? "text-[#4B5563]" : "text-emerald-600"}`}>
                          {appdeployBusy ? <span className="inline-flex items-center gap-1.5"><Loader2 size={11} className="animate-spin" />Provisioning free key…</span> : appdeployMsg}
                        </small>
                      )}
                    </div>
                    {connected ? (
                      <span className="flex shrink-0 items-center gap-1.5 text-xs font-semibold text-emerald-600"><CheckCircle2 size={14} />Connected</span>
                    ) : r.via === "appdeploy" ? (
                      <button onClick={provisionAppDeploy} disabled={appdeployBusy}
                        className="flex shrink-0 items-center gap-1.5 rounded-full bg-[#007AFF]/[.08] px-3.5 py-1.5 text-xs font-bold text-[#007AFF] hover:bg-[#007AFF]/[.14] disabled:opacity-50">
                        {appdeployBusy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}{appdeployBusy ? "…" : "Get free key"}
                      </button>
                    ) : composioKey ? (
                      <button onClick={() => rowAction(r)} aria-label={`Connect ${r.name}`}
                        className="flex shrink-0 items-center gap-1.5 rounded-full bg-[#007AFF]/[.08] px-3.5 py-1.5 text-xs font-bold text-[#007AFF] hover:bg-[#007AFF]/[.14]">
                        <Plus size={13} />Connect
                      </button>
                    ) : (
                      // honest locked state: the gateway key genuinely isn't
                      // stored yet — tapping explains + opens the real key sheet
                      <button onClick={() => setKeySheet("composio")} aria-label={`${r.name} needs Composio`}
                        className="flex shrink-0 items-center gap-1.5 rounded-full border border-[#E5E7EB] px-3.5 py-1.5 text-xs font-medium text-[#6B7280] hover:border-[#007AFF]/40 hover:text-[#007AFF]">
                        <Lock size={13} />Composio
                      </button>
                    )}
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <p className="p-6 text-center text-sm text-[#9CA3AF]">No plugins match "{query}".</p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
