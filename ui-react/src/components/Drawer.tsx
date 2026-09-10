import { useNavigate } from "react-router-dom";
import { Bot, Ghost, LibraryBig, Plus, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

export default function Drawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [chats, setChats] = useState<{ id: string; title: string }[]>([]);
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
            className="fixed left-0 top-0 bottom-0 w-[300px] bg-surface shadow-lift z-50 px-4 pt-[calc(env(safe-area-inset-top)+16px)] overflow-y-auto flex flex-col">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 rounded-xl bg-gradient-to-br from-accent-magenta via-accent to-accent-cyan flex items-center justify-center text-white text-[14px] font-black">A</span>
                <span className="text-[20px] font-black tracking-tight arc-gradient-text">ARC</span>
              </div>
              <button onClick={onClose} aria-label="Close" className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface2"><X size={19} className="text-ink" /></button>
            </div>

            <button onClick={() => go("/chat")}
              className="w-full mt-4 bg-accent text-white rounded-full py-3 font-semibold flex items-center justify-center gap-2 active:scale-[0.98] transition-transform">
              <Plus size={17} /> New chat
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
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-magenta via-accent to-accent-cyan text-white font-bold flex items-center justify-center shrink-0">D</div>
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
