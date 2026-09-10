import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Play, Search, TerminalSquare, X } from "lucide-react";
import { api } from "../lib/api";
import type { ToolInfo } from "../lib/api";
import PageHeader from "../components/PageHeader";

const CATEGORY: Record<string, string> = {
  shell: "System", fs: "System", packages: "System", git: "System", skill: "System", agent_spawn: "System", note: "Core",
  net: "Web", browser: "Web", email: "Email", freqtrade: "Trading", gpt_research: "Research", torbot: "Onion", lab: "Lab",
};
const categoryOf = (name: string) => CATEGORY[name.split(".")[0]] ?? "Core";

/** The real tool registry — every card is a live backend tool; the runner
 * invokes the exact same code path the agent uses. */
export default function SkillsPage() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<ToolInfo | null>(null);

  useEffect(() => { api.tools().then(setTools).catch(() => null).finally(() => setLoaded(true)); }, []);

  const grouped = useMemo(() => {
    const filtered = tools.filter((t) => `${t.name} ${t.description ?? ""}`.toLowerCase().includes(query.toLowerCase()));
    const byCat: Record<string, ToolInfo[]> = {};
    for (const t of filtered) (byCat[categoryOf(t.name)] ??= []).push(t);
    return byCat;
  }, [tools, query]);

  return (
    <div className="mx-auto min-h-full max-w-5xl px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Capabilities / 03" title="Skills" description={`${tools.length} live tools wired to the server — run any of them directly.`} />
      <div className="mb-8">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-3 text-slate-600" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search skills"
            className="arc-focus w-full rounded-xl border border-white/[.09] bg-white/[.035] py-2.5 pl-9 pr-3 text-sm text-white outline-none placeholder:text-slate-600" />
        </div>
      </div>
      {loaded && tools.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/[.12] px-6 py-14 text-center">
          <p className="text-sm text-slate-300">The tool registry isn't reachable right now.</p>
          <p className="mt-2 text-xs text-slate-600">Reload — if this persists the backend didn't finish booting.</p>
        </div>
      )}
      {Object.entries(grouped).map(([cat, list]) => (
        <section key={cat} className="mb-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">{cat}</h2>
            <span className="text-xs text-slate-600">{list.length}</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {list.map((t) => (
              <button key={t.name} onClick={() => setActive(t)} className="arc-card rounded-2xl p-4 text-left hover:border-cyan-300/30 active:scale-[.99]">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-300/10 text-cyan-200"><TerminalSquare size={16} /></span>
                  <b className="truncate text-[13.5px] font-semibold text-white">{t.name}</b>
                </div>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{t.description ?? "Real server tool."}</p>
              </button>
            ))}
          </div>
        </section>
      ))}

      {/* runner bottom sheet — real invocation */}
      <AnimatePresence>
        {active && <ToolRunner tool={active} onClose={() => setActive(null)} />}
      </AnimatePresence>
    </div>
  );
}

function ToolRunner({ tool, onClose }: { tool: ToolInfo; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; output?: string; error?: string } | null>(null);
  const argNames = Object.keys((tool.args as Record<string, unknown>)?.properties ?? {});

  const run = async () => {
    setBusy(true); setResult(null);
    let args: Record<string, unknown> = {};
    try {
      for (const [k, v] of Object.entries(values)) args[k] = v === "" ? undefined : JSON.parse(v);
    } catch {
      for (const [k, v] of Object.entries(values)) args[k] = v === "" ? undefined : v;
    }
    try {
      setResult(await api.invokeTool(tool.name, args));
    } catch (err) {
      setResult({ ok: false, error: (err as Error).message });
    } finally { setBusy(false); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#020313]/70 backdrop-blur-sm sm:items-center">
      <motion.div initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }} onClick={(e) => e.stopPropagation()}
        transition={{ type: "spring", damping: 28, stiffness: 300 }} className="arc-card max-h-[82vh] w-full max-w-xl overflow-y-auto rounded-t-3xl p-5 sm:rounded-3xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-300/10 text-cyan-200"><TerminalSquare size={16} /></span>
            <div><b className="block text-sm font-semibold text-white">{tool.name}</b><small className="text-[11px] text-slate-600">real server invocation</small></div>
          </div>
          <button onClick={onClose} aria-label="Close runner" className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 hover:bg-white/[.07] hover:text-white"><X size={17} /></button>
        </div>
        <p className="mb-4 text-xs leading-5 text-slate-500">{tool.description}</p>
        {argNames.length === 0 ? (
          <p className="mb-4 text-xs text-slate-600">No arguments — hit run.</p>
        ) : argNames.map((name) => (
          <div key={name} className="mb-3">
            <label className="arc-mono mb-1.5 block text-[10px] uppercase tracking-[.2em] text-slate-600">{name}</label>
            <input value={values[name] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
              placeholder={`value for ${name}`}
              className="arc-focus w-full rounded-xl border border-white/[.09] bg-white/[.035] px-3 py-2.5 text-sm text-white outline-none placeholder:text-slate-600" />
          </div>
        ))}
        <button onClick={run} disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 py-2.5 text-sm font-bold text-[#10132f] disabled:opacity-40 active:scale-[.98]">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}Run tool
        </button>
        {result && (
          <div className="mt-4">
            <p className={`arc-mono mb-1.5 text-[10px] uppercase tracking-[.2em] ${result.ok ? "text-emerald-300" : "text-rose-300"}`}>{result.ok ? "Result" : "Failed"}</p>
            <pre className="arc-scroll max-h-56 overflow-auto rounded-xl border border-white/[.07] bg-[#0b0e28] p-3 text-[12px] leading-relaxed text-slate-300">{result.ok ? (result.output ?? "(empty output)") : (result.error ?? "unknown error")}</pre>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
