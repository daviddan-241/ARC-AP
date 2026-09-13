import { useEffect, useState } from "react";
import { Globe, Loader2, Mail, Play, Plus, RefreshCw, Wallet, Zap } from "lucide-react";
import { api } from "../lib/api";
import type { Task } from "../lib/api";
import { useStore } from "../lib/store";
import PageHeader from "../components/PageHeader";

const MONEY_RUNS = [
  { label: "Find money online", goal: "Research realistic, legal ways I can earn money online right now — freelance gigs, bounties, reselling, micro-tasks. Use web search to find CURRENT opportunities with real links and payout details, then rank the top 5 by effort vs. payout and tell me exactly how to start each one." },
  { label: "Build a money-making asset", goal: "Design and start building a small digital product or service that can generate income (template, tool, guide bundle). Research what's selling now, pick one I can build fast with your tools, build the first real version, and report what you made and how to sell it." },
  { label: "Trading edge research", goal: "Research the current crypto/markets landscape with web search and identify 3 concrete, actionable opportunities with entry points, risks, and sources. No financial advice disclaimers — real analysis with numbers." },
];

/** Automations — the REAL autonomous task engine. "Money runs" are real
 * autonomous tasks with money-finding goals the engine actually executes. */
export default function AutomationsPage() {
  const openBrowser = useStore((s) => s.openBrowser);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () => api.tasks().then(setTasks).catch(() => null).finally(() => setLoaded(true));
  useEffect(() => { refresh(); }, []);

  const create = async (g: string) => {
    const v = g.trim();
    if (!v || busy) return;
    setBusy(true);
    try { await api.createTask(v); setGoal(""); await refresh(); } finally { setBusy(false); }
  };

  const act = async (id: string, action: "approve" | "resume" | "cancel") => {
    await api.taskAction(id, action).catch(() => null);
    await refresh();
  };

  const chip = (st: string) =>
    st === "completed" ? "bg-emerald-400/10 text-emerald-600"
    : st === "failed" || st === "blocked_on_permission" ? "bg-rose-400/10 text-rose-600"
    : "bg-black/[.05] text-[#4B5563]";

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Autonomy / 04" title="Automations" description="Hand the agent a goal — it plans, runs real tools, and reports back. Approve anything that needs permission." action={
        <button onClick={refresh} className="flex items-center gap-2 rounded-xl border border-[#E5E7EB] bg-black/[.04] px-4 py-2.5 text-xs font-bold text-[#111827] hover:bg-black/[.06]"><RefreshCw size={14} />Refresh</button>
      } />

      <div className="arc-card mb-8 rounded-3xl p-4 sm:p-5">
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={2}
          placeholder="Describe an automation — e.g. 'monitor price of X and alert me daily'…"
          className="arc-focus w-full resize-none rounded-xl border border-[#E5E7EB] bg-black/[.03] p-3 text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
        <div className="mt-3 flex justify-end">
          <button onClick={() => create(goal)} disabled={busy || !goal.trim()}
            className="flex items-center gap-2 rounded-xl bg-[#6366F1] px-5 py-2.5 text-xs font-bold text-white disabled:opacity-40 active:scale-[.98]">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}Create &amp; run
          </button>
        </div>
      </div>

      {/* money runs — real autonomous tasks with money goals */}
      <div className="mb-8">
        <div className="mb-3 flex items-center gap-2"><Wallet size={15} className="text-[#6366F1]" /><h2 className="text-sm font-semibold text-[#111827]">Money runs</h2></div>
        <p className="mb-3 text-xs text-[#9CA3AF]">One tap starts a real autonomous task — the agent searches, builds, and reports actual opportunities.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {MONEY_RUNS.map((r) => (
            <button key={r.label} onClick={() => create(r.goal)} className="arc-card rounded-2xl p-4 text-left hover:border-[#6366F1]/40 active:scale-[.99]">
              <span className="arc-gradient mb-2.5 flex h-8 w-8 items-center justify-center rounded-xl text-[#111827]"><Wallet size={15} /></span>
              <b className="block text-[13px] font-semibold text-[#111827]">{r.label}</b>
              <small className="mt-1 block text-[11px] leading-4 text-[#9CA3AF]">Autonomous · uses real web search + build tools</small>
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[#111827]">Active runs</h2>
        <span className="text-xs text-[#9CA3AF]">{tasks.length} total</span>
      </div>
      {loaded && tasks.length === 0 && (
        <div className="rounded-2xl border border-dashed border-[#E5E7EB] px-6 py-12 text-center">
          <p className="text-sm text-[#374151]">No automations yet.</p>
          <p className="mt-2 text-xs text-[#9CA3AF]">Describe a goal above, or launch a money run.</p>
        </div>
      )}
      <div className="space-y-3">
        {tasks.map((t) => (
          <div key={t.id} className="arc-card rounded-2xl p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="flex-1 text-[14px] font-semibold leading-5 text-[#111827]">{t.goal}</p>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${chip(t.status)}`}>{t.status}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="arc-mono text-[10.5px] uppercase tracking-[.15em] text-[#9CA3AF]">{t.task_type ?? "goal"}{t.created_at ? ` · ${new Date(t.created_at).toLocaleDateString()}` : ""}</span>
              <span className="flex-1" />
              {t.status === "blocked_on_permission" && <button onClick={() => act(t.id, "approve")} className="rounded-full border border-[#6366F1]/40 px-3 py-1.5 text-[12px] font-semibold text-[#6366F1]">Approve</button>}
              {(t.status === "failed" || t.status === "waiting_retry") && <button onClick={() => act(t.id, "resume")} className="rounded-full border border-[#E5E7EB] px-3 py-1.5 text-[12px] font-medium text-[#374151]">Resume</button>}
              {t.status === "active" && <button onClick={() => act(t.id, "cancel")} className="rounded-full border border-[#E5E7EB] px-3 py-1.5 text-[12px] font-medium text-[#374151]">Cancel</button>}
            </div>
            {t.error && <p className="mt-2 text-xs leading-5 text-rose-600/80">{t.error}</p>}
          </div>
        ))}
      </div>

      {/* hub — real shortcuts: the live browser for logins */}
      <div className="mt-10">
        <h2 className="mb-3 text-sm font-semibold text-[#111827]">Hub</h2>
        <div className="arc-card overflow-hidden rounded-3xl">
          {[
            { label: "Open arena.ai — sign in / use the model", icon: Globe, act: () => openBrowser("https://arena.ai", "arena") },
            { label: "Open the agent's email — sign in once", icon: Mail, act: () => openBrowser("https://mail.google.com", "webmail") },
          ].map(({ label, icon: Icon, act }) => (
            <button key={label} onClick={act} className="flex w-full items-center gap-3 border-b border-[#E5E7EB] p-4 text-left last:border-b-0 hover:bg-black/[.03]">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#6366F1]/10 text-[#6366F1]"><Icon size={16} /></span>
              <span className="flex-1 text-[13.5px] font-medium text-[#111827]">{label}</span>
              <Plus size={15} className="text-[#9CA3AF]" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
