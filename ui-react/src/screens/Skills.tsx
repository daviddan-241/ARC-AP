import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, ChevronRight, FileSpreadsheet, FileText, Presentation, Wand2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import type { ToolInfo } from "../lib/api";

const ICONS = [FileText, Presentation, FileSpreadsheet, Wand2] as const;

/** Skills — the REAL tool registry; every skill is runnable from the UI. */
export default function Skills() {
  const navigate = useNavigate();
  const [tools, setTools] = useState<ToolInfo[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [args, setArgs] = useState("{}");
  const [result, setResult] = useState<{ name: string; out: string } | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  const humanize = (key: string) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const run = async (name: string) => {
    setRunning(true);
    try {
      const parsed = JSON.parse(args || "{}") as Record<string, unknown>;
      const r = await api.invokeTool(name, parsed);
      setResult({ name, out: r.ok ? (r.output ?? "done") : `⚠ ${r.error ?? "failed"}` });
    } catch (e) {
      setResult({ name, out: `⚠ ${(e as Error).message}` });
    } finally { setRunning(false); }
  };

  return (
    <div className="h-full overflow-y-auto px-4 pt-2 pb-8">
      <h1 className="text-[28px] font-bold tracking-tight text-ink">Skills</h1>

      <div className="section-label mt-6 mb-2">My Skills</div>
      <div className="rounded-card bg-surface p-8 flex flex-col items-center text-center gap-3">
        <Bot size={44} strokeWidth={1.5} className="text-ink-dim" />
        <p className="text-[15px] text-ink-dim">No custom skills yet</p>
        <button onClick={() => navigate("/chat")}
          className="bg-accent text-white rounded-full px-6 py-3 font-semibold shadow-soft active:scale-95 transition-transform">
          Create with Arena
        </button>
      </div>

      <div className="section-label mt-6 mb-2">Built-in</div>
      {tools === null && <p className="text-[13px] text-ink-dim py-3">Loading…</p>}
      {tools !== null && tools.length === 0 && (
        <p className="text-[13px] text-ink-dim py-3">Registry unavailable</p>
      )}
      {tools?.map((t, i) => {
        const Icon = ICONS[i % ICONS.length];
        const isOpen = expanded === t.name;
        return (
          <div key={t.name}>
            <button onClick={() => { setExpanded(isOpen ? null : t.name); setResult(null); }}
              className="w-full flex items-center gap-3 p-3.5 rounded-2xl hover:bg-surface2 transition-colors text-left">
              <span className="w-10 h-10 rounded-full bg-surface2 flex items-center justify-center shrink-0">
                <Icon size={18} strokeWidth={1.5} className="text-ink" />
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-[15.5px] font-semibold text-ink">{humanize(t.name)}</span>
                <span className="block text-[13px] text-ink-dim truncate">{t.description ?? "—"}</span>
              </span>
              <ChevronRight size={18} className="text-ink-dim shrink-0" />
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22 }} className="overflow-hidden">
                  <div className="px-3.5 pb-3">
                    <textarea value={args} onChange={(e) => setArgs(e.target.value)} rows={2}
                      placeholder='{"command": "whoami"}'
                      className="w-full font-mono text-[14px] bg-surface rounded-xl p-2.5 border border-line outline-none resize-none" />
                    <button onClick={() => run(t.name)} disabled={running}
                      className="mt-2 bg-accent text-white rounded-full px-5 py-2 text-[14px] font-semibold disabled:opacity-50 active:scale-95 transition-transform">
                      {running ? "Running…" : "Run"}
                    </button>
                    {result?.name === t.name && (
                      <pre className="mt-2 text-[13px] bg-surface rounded-xl p-3 overflow-auto max-h-48 whitespace-pre-wrap">{result.out}</pre>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
