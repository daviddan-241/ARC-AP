import { useEffect, useState } from "react";
import { Loader2, MessageSquarePlus, RefreshCw, Trash2 } from "lucide-react";
import { api, type Conversation } from "../lib/api";
import { useStore } from "../lib/store";

/** Real chat history: lists actual conversations from the backend (no mock),
 * lets you switch, start a new one, or delete one. Used in both the desktop
 * sidebar and the mobile drawer so "recent chats" genuinely exists — before
 * this there was no way to see or return to a past conversation at all. */
export default function ChatHistory({ onNavigate }: { onNavigate?: () => void }) {
  const conversationId = useStore((s) => s.conversationId);
  const setConversation = useStore((s) => s.setConversation);
  const resetChat = useStore((s) => s.resetChat);
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true); setErr("");
    try {
      setItems(await api.listConversations());
    } catch {
      setErr("Couldn't load history — check your connection.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [conversationId]);

  const startNew = () => {
    setConversation(null);
    resetChat();
    onNavigate?.();
  };

  const open = (id: string) => {
    setConversation(id);
    onNavigate?.();
  };

  const remove = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      setItems((prev) => prev.filter((c) => c.id !== id));
      if (id === conversationId) startNew();
    } catch { /* real error, but deleting is best-effort here — refresh will show truth */ }
  };

  return (
    <div className="min-w-0">
      <button onClick={startNew}
        className="arc-transition mb-2 flex w-full items-center gap-3 rounded-xl border border-white/[.09] px-3 py-2.5 text-sm font-medium text-slate-200 hover:border-cyan-300/30 hover:bg-white/[.05] hover:text-white active:scale-[.98]">
        <MessageSquarePlus size={16} className="text-cyan-300" />New chat
      </button>
      <div className="mb-1.5 flex items-center justify-between px-3">
        <p className="arc-mono text-[10px] uppercase tracking-[.22em] text-slate-600">Recent</p>
        <button aria-label="Refresh history" onClick={load} className="text-slate-600 hover:text-slate-300">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {loading && items.length === 0 && (
        <div className="flex items-center gap-2 px-3 py-2 text-[12.5px] text-slate-600"><Loader2 size={13} className="animate-spin" />Loading…</div>
      )}
      {err && <p className="px-3 py-2 text-[12px] text-rose-300">{err}</p>}
      {!loading && !err && items.length === 0 && (
        <p className="px-3 py-2 text-[12px] text-slate-600">No chats yet — start one above.</p>
      )}
      <div className="max-h-[38vh] space-y-0.5 overflow-y-auto">
        {items.map((c) => (
          <button key={c.id} onClick={() => open(c.id)}
            className={`group arc-transition flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-[13px] ${c.id === conversationId ? "bg-white/[.1] text-white" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>
            <span className="min-w-0 flex-1 truncate">{c.title || "Untitled chat"}</span>
            <span onClick={(e) => remove(c.id, e)} role="button" aria-label="Delete chat"
              className="shrink-0 rounded-lg p-1 text-slate-600 opacity-0 hover:bg-rose-400/10 hover:text-rose-300 group-hover:opacity-100">
              <Trash2 size={13} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
