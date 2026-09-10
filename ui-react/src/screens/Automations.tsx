import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Clock, Globe, MessageCircle, Pin, Zap } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import type { Task } from "../lib/api";
import { useStore } from "../lib/store";

/** Automations — the REAL autonomous task engine + the Grok-style hub. */
export default function Automations() {
  const navigate = useNavigate();
  const openBrowser = useStore((s) => s.openBrowser);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [composing, setComposing] = useState(false);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () => api.tasks().then((t) => { setTasks(t); setLoaded(true); }).catch(() => setLoaded(true));
  useEffect(() => { refresh(); }, []);

  const create = async () => {
    if (!goal.trim() || busy) return;
    setBusy(true);
    try {
      await api.createTask(goal.trim());
      setGoal("");
      setComposing(false);
      await refresh();
    } finally { setBusy(false); }
  };

  const act = async (id: string, action: "approve" | "resume" | "cancel") => {
    await api.taskAction(id, action).catch(() => null);
    await refresh();
  };

  const statusChip = (st: string) =>
    st === "completed" ? "bg-[#22C55E]/10 text-success"
    : st === "failed" || st === "blocked_on_permission" ? "bg-red-50 text-red-500"
    : "bg-surface2 text-ink-dim";

  const hubRows = [
    { label: "Automations", icon: Zap, act: refresh },
    { label: "Companions", icon: Bot, act: () => navigate("/skills") },
    { label: "Pinned chats", icon: Pin, act: () => navigate("/library") },
    { label: "Discord servers", icon: MessageCircle, act: () => openBrowser("https://discord.com") },
    { label: "OPEN CLAW", icon: Globe, act: () => openBrowser("https://arena.ai") },
  ] as const;

  return (
    <div className="h-full overflow-y-auto px-4 pt-2 pb-8">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-bold tracking-tight text-ink">Automations</h1>
        <button onClick={() => setComposing(true)}
          className="bg-ink text-white rounded-full px-4 py-2 text-[13px] font-semibold shadow-soft active:scale-95 transition-transform">
          + New Automation
        </button>
      </div>

      {loaded && tasks.length === 0 && (
        <div className="flex flex-col items-center text-center gap-4 py-14">
          <Clock size={56} strokeWidth={1} className="text-ink-dim" />
          <p className="text-[16px] text-ink-dim">Start by adding an automation</p>
          <button onClick={() => setComposing(true)}
            className="bg-ink text-white rounded-full px-6 py-3 font-semibold shadow-soft active:scale-95 transition-transform">
            + New Automation
          </button>
        </div>
      )}

      <AnimatePresence initial={false}>
        {composing && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }} className="overflow-hidden">
            <div className="rounded-card border border-line bg-white p-4 mt-4 shadow-soft">
              <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3}
                placeholder="Describe an automation…"
                className="w-full bg-surface rounded-xl p-3 text-[15px] border border-line outline-none resize-none" />
              <div className="flex gap-2 mt-2">
                <button onClick={create} disabled={busy || !goal.trim()}
                  className="bg-accent text-white rounded-full px-5 py-2 text-[14px] font-semibold disabled:opacity-40 active:scale-95 transition-transform">
                  {busy ? "Starting…" : "Create & run"}
                </button>
                <button onClick={() => setComposing(false)}
                  className="border border-line rounded-full px-4 py-2 text-[14px] text-ink-dim">Cancel</button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-4">
        {tasks.map((t) => (
          <div key={t.id} className="mb-3 rounded-card border border-line bg-white p-4 shadow-soft">
            <div className="flex items-start justify-between gap-3">
              <p className="text-[15px] font-semibold text-ink flex-1">{t.goal}</p>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-[12px] font-semibold ${statusChip(t.status)}`}>{t.status}</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[12.5px] text-ink-dim">{t.task_type ?? "goal"}{t.created_at ? ` · ${new Date(t.created_at).toLocaleDateString()}` : ""}</span>
              <span className="flex-1" />
              {t.status === "blocked_on_permission" && (
                <button onClick={() => act(t.id, "approve")} className="border border-line rounded-full px-3 py-1.5 text-[13px] font-medium text-ink">Approve</button>
              )}
              {(t.status === "failed" || t.status === "waiting_retry") && (
                <button onClick={() => act(t.id, "resume")} className="border border-line rounded-full px-3 py-1.5 text-[13px] font-medium text-ink">Resume</button>
              )}
              {t.status === "active" && (
                <button onClick={() => act(t.id, "cancel")} className="border border-line rounded-full px-3 py-1.5 text-[13px] font-medium text-ink">Cancel</button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="section-label mt-6 mb-1">Hub</div>
      {hubRows.map(({ label, icon: Icon, act }) => (
        <button key={label} onClick={() => act()} className="w-full flex items-center gap-3 py-3 text-left hover:bg-surface rounded-2xl px-1 transition-colors">
          <span className="w-10 h-10 rounded-full bg-surface2 flex items-center justify-center shrink-0">
            <Icon size={18} strokeWidth={1.5} className="text-ink" />
          </span>
          <span className="flex-1 text-[15px] font-medium text-ink">{label}</span>
        </button>
      ))}
    </div>
  );
}
