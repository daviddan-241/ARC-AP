import { useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Search, Trash2, X } from "lucide-react";
import { api, type Conversation } from "../lib/api";
import { useStore } from "../lib/store";

/** Real chat history: lists actual conversations from the backend (no mock),
 * lets you search, switch, or delete one. "New chat" itself lives as the
 * pinned bottom action in the sidebar (see App.tsx Shell) so it always
 * stays reachable even while this list scrolls — matching the reference
 * layout where Library/Projects/Plugins/More sit above "Recents" and the
 * new-chat action is pinned at the very bottom next to the profile icon. */
export default function ChatHistory({ onNavigate }: { onNavigate?: () => void }) {
  const conversationId = useStore((s) => s.conversationId);
  const setConversation = useStore((s) => s.setConversation);
  const resetChat = useStore((s) => s.resetChat);
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");

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

  const open = (id: string) => {
    setConversation(id);
    onNavigate?.();
  };

  const remove = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      setItems((prev) => prev.filter((c) => c.id !== id));
      if (id === conversationId) { setConversation(null); resetChat(); }
    } catch { /* real error, but deleting is best-effort here — refresh will show truth */ }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((c) => (c.title || "untitled chat").toLowerCase().includes(q));
  }, [items, query]);

  return (
    <div className="min-w-0">
      {/* real search over your actual chat titles -- client-side filter of
         the same list already loaded, not a decorative icon */}
      <div className="mb-3 flex items-center gap-2 rounded-xl border border-white/[.09] bg-white/[.03] px-3 py-2 focus-within:border-cyan-300/30">
        <Search size={14} className="shrink-0 text-slate-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search chats"
          className="w-full bg-transparent text-[13px] text-white outline-none placeholder:text-slate-600" />
        {query && (
          <button onClick={() => setQuery("")} aria-label="Clear search" className="text-slate-500 hover:text-white">
            <X size={13} />
          </button>
        )}
      </div>
      <div className="mb-1.5 flex items-center justify-between px-1">
        <p className="text-[12.5px] font-semibold text-slate-300">Recents</p>
        <button aria-label="Refresh history" onClick={load} className="text-slate-600 hover:text-slate-300">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {loading && items.length === 0 && (
        <div className="flex items-center gap-2 px-3 py-2 text-[12.5px] text-slate-600"><Loader2 size={13} className="animate-spin" />Loading…</div>
      )}
      {err && <p className="px-3 py-2 text-[12px] text-rose-300">{err}</p>}
      {!loading && !err && items.length === 0 && (
        <p className="px-3 py-2 text-[12px] text-slate-600">No chats yet — tap "New chat" below to start one.</p>
      )}
      {!loading && !err && items.length > 0 && filtered.length === 0 && (
        <p className="px-3 py-2 text-[12px] text-slate-600">No chats match "{query}".</p>
      )}
      <div className="max-h-[42vh] space-y-0.5 overflow-y-auto">
        {filtered.map((c) => (
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
