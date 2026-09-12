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
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Surfaces / 08" title="Browser" description="The agent's real browser, streamed live. Log into anything here — the session stays on the server." />
      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        <button onClick={() => go("https://arena.ai", "arena")} className="arc-card flex items-center gap-3 rounded-2xl p-4 text-left hover:border-[#007AFF]/40 active:scale-[.99]">
          <span className="arc-gradient flex h-10 w-10 items-center justify-center rounded-xl text-[#111827]"><Globe size={17} /></span>
          <span className="flex-1"><b className="block text-sm font-semibold text-[#111827]">arena.ai</b><small className="text-[11px] text-[#9CA3AF]">The model session — sign in once</small></span>
          <ArrowUpRight size={15} className="text-[#9CA3AF]" />
        </button>
        <button onClick={() => go("https://mail.google.com", "webmail")} className="arc-card flex items-center gap-3 rounded-2xl p-4 text-left hover:border-[#007AFF]/40 active:scale-[.99]">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-400/15 text-violet-600"><Mail size={17} /></span>
          <span className="flex-1"><b className="block text-sm font-semibold text-[#111827]">Agent email</b><small className="text-[11px] text-[#9CA3AF]">The inbox it reads codes from</small></span>
          <ArrowUpRight size={15} className="text-[#9CA3AF]" />
        </button>
      </div>
      <div className="arc-card rounded-3xl p-5">
        <p className="arc-mono mb-3 text-[10px] uppercase tracking-[.22em] text-[#007AFF]/70">Open any site</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="discord.com, your bank, anything…"
            onKeyDown={(e) => { if (e.key === "Enter" && url.trim()) go(/^https?:\/\//.test(url.trim()) ? url.trim() : `https://${url.trim()}`, "free"); }}
            className="arc-focus flex-1 rounded-xl border border-[#E5E7EB] bg-black/[.03] px-3 py-2.5 text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
          <button onClick={() => url.trim() && go(/^https?:\/\//.test(url.trim()) ? url.trim() : `https://${url.trim()}`, "free")}
            className="flex items-center justify-center gap-2 rounded-xl bg-[#007AFF] px-5 py-2.5 text-xs font-bold text-white active:scale-[.98]">
            <Zap size={14} />Launch
          </button>
        </div>
      </div>
    </div>
  );
}
