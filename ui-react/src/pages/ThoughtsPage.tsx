import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, Trash2 } from "lucide-react";
import { useStore } from "../lib/store";
import PageHeader from "../components/PageHeader";

/** The real thoughts feed: live tool steps + sources from actual agent turns,
 * streamed from the backend as they happen. */
export default function ThoughtsPage() {
  const steps = useStore((s) => s.steps);
  const sources = useStore((s) => s.sources);
  const clearThoughts = useStore((s) => s.clearThoughts);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Reasoning / 02" title="Thoughts" description="The agent's live exploration — every tool it runs, every result it gets, as it happens." action={
        steps.length > 0 || sources.length > 0 ? (
          <button onClick={clearThoughts} className="flex items-center gap-2 rounded-xl border border-white/[.1] bg-white/[.04] px-4 py-2.5 text-xs font-bold text-white hover:bg-white/[.08]"><Trash2 size={14} />Clear run</button>
        ) : undefined
      } />
      {steps.length === 0 && sources.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/[.12] px-6 py-16 text-center">
          <p className="text-sm text-slate-300">Nothing yet.</p>
          <p className="mt-2 text-xs text-slate-600">Send a message in Chat and the agent's live steps will stream in here.</p>
        </div>
      ) : (
        <div className="arc-card overflow-hidden rounded-2xl">
          {steps.map((st) => (
            <div key={st.id} className="border-b border-white/[.05] last:border-b-0">
              <button onClick={() => setOpenId(openId === st.id ? null : st.id)} className="flex w-full items-center gap-3 p-4 text-left hover:bg-white/[.02]">
                {st.state === "ok" ? <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10"><Check size={13} strokeWidth={3} className="text-emerald-300" /></span>
                  : st.state === "running" ? <Loader2 size={16} className="shrink-0 animate-spin text-cyan-300" />
                  : <span className="h-7 w-7 shrink-0 rounded-lg border-2 border-rose-400/40" />}
                <span className="min-w-0 flex-1 text-[13.5px] text-white">{st.label}</span>
                {st.detail && (openId === st.id ? <ChevronDown size={14} className="text-slate-600" /> : <ChevronRight size={14} className="text-slate-600" />)}
              </button>
              {openId === st.id && st.detail && (
                <pre className="arc-scroll overflow-x-auto border-t border-white/[.05] bg-[#0b0e28] px-4 py-3 text-[12px] leading-relaxed text-slate-400">{st.detail}</pre>
              )}
            </div>
          ))}
        </div>
      )}
      {sources.length > 0 && (
        <>
          <div className="mb-3 mt-8 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Sources</h2>
            <span className="text-xs text-slate-600">{sources.length} found</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {sources.map((src, i) => (
              <a key={i} href={src.url} target="_blank" rel="noreferrer" className="arc-card flex items-center gap-3 rounded-2xl p-4 hover:border-cyan-300/30">
                {src.logo ? <img src={src.logo} alt="" className="h-8 w-8 rounded-lg" /> : <div className="arc-gradient h-8 w-8 rounded-lg" />}
                <span className="min-w-0 flex-1"><b className="block truncate text-sm text-white">{src.title}</b><small className="text-xs text-slate-600">{src.domain}</small></span>
              </a>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
