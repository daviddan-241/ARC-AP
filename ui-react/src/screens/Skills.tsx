import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Globe, Search, Terminal, Mail, TrendingUp, BookOpen, Shield, Ghost, Bot,
  Sparkles, Cpu, Zap, ChevronRight, Play, X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import type { ToolInfo } from "../lib/api";

/** A real skill = a registry tool. Grouped into bold category cards; every
 * card expands into a live runner (args editor + real result). */

type Category = {
  key: string;
  label: string;
  match: (n: string) => boolean;
  icon: typeof Globe;
  blurb: string;
};

const CATEGORIES: Category[] = [
  { key: "web", label: "Web", blurb: "Browse, search, fetch", icon: Globe,
    match: (n) => /^(web_|http|fetch|browse|search|scrape|web_search)/.test(n) },
  { key: "email", label: "Email", blurb: "The agent's own inbox", icon: Mail,
    match: (n) => /^email_/.test(n) },
  { key: "trading", label: "Trading", blurb: "Freqtrade backtests", icon: TrendingUp,
    match: (n) => /^(freqtrade|crypto|trading|market_)/.test(n) },
  { key: "research", label: "Research", blurb: "Deep multi-source reports", icon: BookOpen,
    match: (n) => /^(gpt_research|research|deep_)/.test(n) },
  { key: "darkweb", label: "Onion", blurb: "Tor crawls via TorBot", icon: Ghost,
    match: (n) => /^(torbot|onion|tor_)/.test(n) },
  { key: "security", label: "Security", blurb: "Recon & offensive tooling", icon: Shield,
    match: (n) => /(hack|recon|scan|nmap|port|threat|pentest|vuln|exploit)/.test(n) },
  { key: "system", label: "System", blurb: "Shell, files, processes", icon: Terminal,
    match: (n) => /^(shell|command|run_|process|file_|download|install|read_|write_|upload|workspace|fs_)/.test(n) },
  { key: "core", label: "Core", blurb: "Self-management & memory", icon: Cpu,
    match: (n) => /(memory|note|setting|upgrade|lab|self_|plugin|automation|schedule|skill|subagent|persona|model)/.test(n) },
];

const classify = (name: string): Category =>
  CATEGORIES.find((c) => c.match(name)) ??
  { key: "more", label: "More", blurb: "Everything else", icon: Sparkles, match: () => false };

const humanize = (key: string) =>
  key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function Skills() {
  const navigate = useNavigate();
  const [tools, setTools] = useState<ToolInfo[] | null>(null);
  const [run, setRun] = useState<ToolInfo | null>(null);
  const [args, setArgs] = useState("{}");
  const [result, setResult] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  const groups = useMemo(() => {
    const map = new Map<string, ToolInfo[]>();
    for (const t of tools ?? []) {
      const k = classify(t.name).key;
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(t);
    }
    return map;
  }, [tools]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return groups;
    const m = new Map<string, ToolInfo[]>();
    for (const [k, list] of groups)
      m.set(k, list.filter((t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description ?? "").toLowerCase().includes(q)));
    return m;
  }, [groups, query]);

  const openRunner = (t: ToolInfo) => {
    setRun(t);
    setResult("");
    let seed = "{}";
    try {
      const a = (t as { args?: Record<string, unknown> }).args;
      if (a && Object.keys(a).length) seed = JSON.stringify(a, null, 2);
    } catch { /* keep default seed */ }
    setArgs(seed);
  };

  const execute = async () => {
    if (!run) return;
    setRunning(true);
    setResult("");
    try {
      const parsed = JSON.parse(args || "{}") as Record<string, unknown>;
      const r = await api.invokeTool(run.name, parsed);
      setResult(r.ok ? (r.output ?? "done") : `⚠ ${r.error ?? "failed"}`);
    } catch (e) {
      setResult(`⚠ ${(e as Error).message}`);
    } finally { setRunning(false); }
  };

  return (
    <div className="h-full overflow-y-auto px-4 pt-2 pb-8">
      <div className="flex items-end justify-between">
        <h1 className="text-[30px] font-black tracking-tight text-ink">Skills</h1>
        <span className="text-[13px] font-semibold text-ink-dim mb-1.5">
          {tools?.length ?? "…"} live
        </span>
      </div>

      <div className="mt-4 flex items-center gap-2 bg-surface rounded-full px-4 py-2.5 border border-line">
        <Search size={15} className="text-ink-dim shrink-0" />
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search skills"
          className="flex-1 bg-transparent outline-none text-[16px] text-ink min-w-0" />
      </div>

      {/* My skills: real skill-library playbooks (SKILL.md) */}
      <div className="section-label mt-6 mb-2">My Skills</div>
      <button onClick={() => navigate("/chat")}
        className="w-full rounded-card border border-line bg-surface p-4 flex items-center gap-4 text-left active:scale-[0.99] transition-transform">
        <span className="w-12 h-12 rounded-2xl bg-gradient-to-br from-accent-magenta via-accent to-accent-cyan flex items-center justify-center shrink-0">
          <Bot size={22} className="text-white" />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-[15.5px] font-bold text-ink">Create a new skill</span>
          <span className="block text-[13px] text-ink-dim">Ask ARC in chat — it writes real SKILL.md playbooks, installed instantly</span>
        </span>
        <ChevronRight size={18} className="text-ink-dim shrink-0" />
      </button>

      {/* Registry tools, grouped into bold category cards */}
      {tools === null && <p className="text-[13px] text-ink-dim py-4">Loading registry…</p>}
      {tools !== null && tools.length === 0 && (
        <p className="text-[13px] text-ink-dim py-4">Registry unavailable — is the server up?</p>
      )}

      {[...shown.entries()].map(([key, list]) => {
        if (!list.length) return null;
        const cat = key === "more" ? classify(list[0].name) : CATEGORIES.find((c) => c.key === key)!;
        const Icon = cat.icon;
        return (
          <div key={key}>
            <div className="section-label mt-6 mb-2">{cat.label}</div>
            <div className="grid grid-cols-2 gap-2.5">
              {list.map((t) => (
                <button key={t.name} onClick={() => openRunner(t)}
                  className="rounded-2xl border border-line bg-surface p-3.5 flex flex-col items-start gap-2.5 text-left active:scale-[0.97] transition-transform">
                  <span className="w-9 h-9 rounded-xl bg-surface2 flex items-center justify-center shrink-0">
                    <Icon size={16} strokeWidth={1.7} className="text-accent" />
                  </span>
                  <span className="w-full">
                    <span className="block text-[14px] font-bold text-ink leading-tight">{humanize(t.name)}</span>
                    <span className="block text-[11.5px] text-ink-dim leading-snug mt-0.5 line-clamp-2">
                      {t.description ?? cat.blurb}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        );
      })}

      {/* runner sheet */}
      <AnimatePresence>
        {run && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setRun(null)} className="fixed inset-0 bg-black/50 z-40" />
            <motion.div
              initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 36 }}
              className="fixed left-0 right-0 bottom-0 z-50 bg-surface rounded-t-3xl border-t border-line
                         px-5 pt-4 pb-[calc(env(safe-area-inset-bottom)+18px)] max-h-[78%] flex flex-col">
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-2xl bg-gradient-to-br from-accent-magenta via-accent to-accent-cyan flex items-center justify-center shrink-0">
                  <Play size={17} className="text-white" />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-[16px] font-bold text-ink truncate">{humanize(run.name)}</span>
                  <span className="block text-[12px] text-ink-dim truncate">{run.description ?? ""}</span>
                </span>
                <button onClick={() => setRun(null)} aria-label="Close"
                  className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface2">
                  <X size={18} className="text-ink" />
                </button>
              </div>
              <textarea value={args} onChange={(e) => setArgs(e.target.value)} rows={4} spellCheck={false}
                placeholder='{"command": "whoami"}'
                className="mt-3 w-full font-mono text-[16px] bg-surface2 rounded-xl p-3 border border-line outline-none resize-none" />
              <button onClick={execute} disabled={running}
                className="mt-3 w-full bg-gradient-to-r from-accent-magenta via-accent to-accent-cyan text-white rounded-full py-3 font-bold flex items-center justify-center gap-2 disabled:opacity-50 active:scale-[0.98] transition-transform">
                {running ? <><Zap size={16} className="animate-pulse" /> Running…</> : <><Play size={16} /> Run</>}
              </button>
              {result && (
                <pre className="mt-3 text-[13px] font-mono text-ink bg-surface2 rounded-xl p-3 border border-line overflow-auto max-h-52 whitespace-pre-wrap">{result}</pre>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
