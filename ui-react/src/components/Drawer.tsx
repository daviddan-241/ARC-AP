import { useNavigate } from "react-router-dom";
import { Bot, ChevronRight, Ghost, LibraryBig, Plus, Sparkles, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

export default function Drawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [chats, setChats] = useState<{ id: string; title: string }[]>([]);
  const openBrowser = useStore((s) => s.openBrowser);
  const setConversation = useStore((s) => s.setConversation);

  useEffect(() => {
    if (open) api.listConversations().then(setChats).catch(() => setChats([]));
  }, [open]);

  const go = (path: string) => { onClose(); navigate(path); };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose} className="fixed inset-0 bg-black/30 z-40" />
          <motion.div initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
            className="fixed left-0 top-0 bottom-0 w-[300px] bg-white shadow-lift z-50 px-4 pt-[calc(env(safe-area-inset-top)+16px)] overflow-y-auto flex flex-col">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot size={22} strokeWidth={1.7} className="text-accent" />
                <span className="text-[17px] font-bold text-ink">ArenaOS</span>
              </div>
              <button onClick={onClose} aria-label="Close" className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface"><X size={19} className="text-ink" /></button>
            </div>

            <button onClick={() => go("/chat")}
              className="w-full mt-4 bg-accent text-white rounded-full py-3 font-semibold flex items-center justify-center gap-2 active:scale-[0.98] transition-transform">
              <Plus size={17} /> New chat
            </button>

            <button onClick={() => openBrowser("https://arena.ai")}
              className="mt-4 rounded-card bg-surface2 p-3.5 flex gap-3 items-center text-left active:scale-[0.99] transition-transform">
              <Sparkles size={18} className="text-accent shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[14px] font-semibold text-ink">Try SuperGrok</div>
                <div className="text-[12px] text-ink-dim">Early access to new features</div>
              </div>
              <ChevronRight size={16} className="text-ink-dim shrink-0" />
            </button>

            <div className="mt-5">
              {([
                { label: "Automations", icon: Zap, path: "/automations" },
                { label: "Companions", icon: Bot, path: "/skills" },
                { label: "Private Chat", icon: Ghost, path: "/private" },
                { label: "Library", icon: LibraryBig, path: "/library" },
              ] as const).map(({ label, icon: Icon, path }) => (
                <button key={label} onClick={() => go(path)} className="w-full flex items-center gap-3 py-2.5">
                  <Icon size={19} strokeWidth={1.5} className="text-ink-dim" />
                  <span className="text-[15px] font-medium text-ink">{label}</span>
                </button>
              ))}
            </div>

            <div className="section-label mt-5 mb-1">Recent</div>
            <div className="flex-1">
              {chats.map((c) => (
                <button key={c.id} onClick={() => { setConversation(c.id); go("/chat"); }}
                  className="w-full text-left py-2.5 text-[14px] text-ink truncate hover:text-accent">{c.title || "Untitled"}</button>
              ))}
              {chats.length === 0 && <p className="text-[13px] text-ink-dim py-2.5">No conversations yet</p>}
            </div>

            <div className="border-t border-line mt-4 pt-4 pb-6 flex gap-3 items-center">
              <div className="w-9 h-9 rounded-full bg-accent text-white font-bold flex items-center justify-center shrink-0">D</div>
              <div>
                <div className="text-[14.5px] font-semibold text-ink">Danny</div>
                <div className="text-[12px] text-ink-dim">operator</div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
