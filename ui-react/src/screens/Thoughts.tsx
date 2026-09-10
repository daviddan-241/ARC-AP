import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, MoreHorizontal, ChevronDown, Check, Bookmark, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../lib/store";
import SourceCard from "../components/SourceCard";
import { api } from "../lib/api";

/** Screen 1 from the spec — the full Grok-style Thoughts view. */
export default function Thoughts() {
  const navigate = useNavigate();
  const steps = useStore((s) => s.steps);
  const sources = useStore((s) => s.sources);
  const [openSection, setOpenSection] = useState(true);
  const [bookmarked, setBookmarked] = useState<Record<string, boolean>>({});
  const [pinnedNote, setPinnedNote] = useState<string | null>(null);

  useEffect(() => {
    // real memory: show the latest learned memory as the pinned note, if any
    api.memory().then((mems) => {
      const latest = mems[mems.length - 1];
      if (latest) setPinnedNote(latest.content.slice(0, 120));
    }).catch(() => setPinnedNote(null));
  }, []);

  const label = steps.length ? steps[steps.length - 1].label : "Exploring";
  const sectionTitle = label.startsWith("Exploring") ? label : `Exploring ${label.toLowerCase()}`;

  return (
    <div className="h-full flex flex-col bg-bg">
      {/* header: back + Thoughts + more menu (exact mockup) */}
      <div className="flex items-center justify-between px-4 pt-[calc(env(safe-area-inset-top)+8px)] pb-3 border-b border-line">
        <button onClick={() => navigate(-1)} aria-label="Back" className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface active:scale-95 transition-all">
          <ArrowLeft size={20} strokeWidth={1.8} className="text-ink" />
        </button>
        <h1 className="text-[17px] font-semibold text-ink">Thoughts</h1>
        <button aria-label="More" className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface">
          <MoreHorizontal size={20} strokeWidth={1.8} className="text-ink" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* expandable section with chevron */}
        <button onClick={() => setOpenSection(!openSection)} className="w-full flex items-center justify-between bg-surface rounded-card px-4 py-3.5 mb-4">
          <span className="text-[15px] font-semibold text-ink text-left truncate pr-2">{sectionTitle}</span>
          <ChevronDown size={18} strokeWidth={2} className={`text-ink-dim transition-transform ${openSection ? "" : "-rotate-90"}`} />
        </button>

        <AnimatePresence initial={false}>
          {openSection && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.28, ease: [0.2, 0.7, 0.2, 1] }} className="overflow-hidden">
              {/* loading state */}
              {steps.some((s) => s.state === "running") && (
                <div className="flex items-center gap-2.5 px-2 py-2.5 text-[14px] text-ink-dim">
                  <Loader2 size={15} className="animate-spin" />
                  Searching across the web…
                </div>
              )}

              {/* SEARCH RESULTS */}
              {sources.length > 0 && (
                <div className="mt-2">
                  <div className="section-label px-1 mb-2">SEARCH RESULTS</div>
                  {sources.map((s, i) => (
                    <SourceCard
                      key={`${s.url}-${i}`}
                      source={{ ...s, ago: s.ago ?? "just now" }}
                      bookmarked={Boolean(bookmarked[s.url])}
                      onBookmark={() => setBookmarked((b) => ({ ...b, [s.url]: !b[s.url] }))}
                    />
                  ))}
                </div>
              )}

              {/* EXPLORATION PROGRESS — green checks + one open circle */}
              <div className="mt-5">
                <div className="section-label px-1 mb-2">EXPLORATION PROGRESS</div>
                {steps.map((st) => (
                  <div key={st.id} className="flex items-start gap-2.5 px-1 py-2">
                    {st.state === "ok" ? (
                      <span className="w-5 h-5 rounded-full bg-[#22C55E]/10 flex items-center justify-center shrink-0">
                        <Check size={12} strokeWidth={3} className="text-success" />
                      </span>
                    ) : st.state === "running" ? (
                      <span className="w-5 h-5 rounded-full border-2 border-line border-t-accent animate-spin shrink-0" />
                    ) : (
                      <span className="w-5 h-5 rounded-full border-2 border-line shrink-0" />
                    )}
                    <div className="text-[14px] text-ink leading-snug">
                      {st.label}
                      {st.detail && <div className="text-[12.5px] text-ink-dim mt-0.5">{st.detail.slice(0, 160)}</div>}
                    </div>
                  </div>
                ))}
                <div className="flex items-start gap-2.5 px-1 py-2">
                  <span className="w-5 h-5 rounded-full border-2 border-line shrink-0" />
                  <div className="text-[14px] text-ink-dim">Next step</div>
                </div>
              </div>

              {pinnedNote && (
                <div className="mt-4 flex items-start gap-2 bg-surface rounded-card p-3.5">
                  <Bookmark size={14} className="text-ink-dim mt-0.5 shrink-0" />
                  <div className="text-[13px] text-ink-dim leading-snug">Latest memory: {pinnedNote}</div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
