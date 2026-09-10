import { useState } from "react";
import { ArrowUpRight, Globe, Mail, Zap } from "lucide-react";
import { useStore } from "../lib/store";
import PageHeader from "../components/PageHeader";

/** Browser hub: launch the real live browser (server-side Chromium streamed
 * over WebSocket) at any site — the login surface for arena.ai and email. */
export default function BrowserPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const [url, setUrl] = useState("");

  const go = (target: string, page: "arena" | "webmail" | "free" = "free") => openBrowser(target, page);

  return (
    <div className="mx-auto min-h-full max-w-5xl px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Surfaces / 08" title="Browser" description="The agent's real browser, streamed live. Log into anything here — the session stays on the server." />
      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        <button onClick={() => go("https://arena.ai", "arena")} className="arc-card flex items-center gap-3 rounded-2xl p-4 text-left hover:border-cyan-300/30 active:scale-[.99]">
          <span className="arc-gradient flex h-10 w-10 items-center justify-center rounded-xl text-[#10132f]"><Globe size={17} /></span>
          <span className="flex-1"><b className="block text-sm font-semibold text-white">arena.ai</b><small className="text-[11px] text-slate-600">The model session — sign in once</small></span>
          <ArrowUpRight size={15} className="text-slate-600" />
        </button>
        <button onClick={() => go("https://mail.google.com", "webmail")} className="arc-card flex items-center gap-3 rounded-2xl p-4 text-left hover:border-cyan-300/30 active:scale-[.99]">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-400/15 text-violet-200"><Mail size={17} /></span>
          <span className="flex-1"><b className="block text-sm font-semibold text-white">Agent email</b><small className="text-[11px] text-slate-600">The inbox it reads codes from</small></span>
          <ArrowUpRight size={15} className="text-slate-600" />
        </button>
      </div>
      <div className="arc-card rounded-3xl p-5">
        <p className="arc-mono mb-3 text-[10px] uppercase tracking-[.22em] text-cyan-300/70">Open any site</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="discord.com, your bank, anything…"
            onKeyDown={(e) => { if (e.key === "Enter" && url.trim()) go(/^https?:\/\//.test(url.trim()) ? url.trim() : `https://${url.trim()}`, "free"); }}
            className="arc-focus flex-1 rounded-xl border border-white/[.09] bg-white/[.035] px-3 py-2.5 text-sm text-white outline-none placeholder:text-slate-600" />
          <button onClick={() => url.trim() && go(/^https?:\/\//.test(url.trim()) ? url.trim() : `https://${url.trim()}`, "free")}
            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 px-5 py-2.5 text-xs font-bold text-[#10132f] active:scale-[.98]">
            <Zap size={14} />Launch
          </button>
        </div>
      </div>
    </div>
  );
}
