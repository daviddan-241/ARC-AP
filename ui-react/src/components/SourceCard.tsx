import { useNavigate } from "react-router-dom";
import { Bookmark } from "lucide-react";
import { faviconUrl } from "../lib/store";
import type { SourceResult } from "../lib/store";

/** Grok-style search result card: logo circle + domain + time ago, bold title,
 * snippet, bookmark icon. Clicking the card opens the URL in the in-app browser. */
export default function SourceCard({
  source,
  bookmarked = false,
  onBookmark,
}: {
  source: SourceResult & { ago?: string };
  bookmarked?: boolean;
  onBookmark?: () => void;
}) {
  const navigate = useNavigate();
  const openBrowser = (url: string) => {
    window.dispatchEvent(new CustomEvent("open-browser", { detail: url }));
    navigate("/chat");
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openBrowser(source.url)}
      onKeyDown={(e) => e.key === "Enter" && openBrowser(source.url)}
      className="w-full flex items-start gap-3 bg-surface rounded-card px-3.5 py-3 mb-2 text-left hover:bg-surface2 transition-colors cursor-pointer active:scale-[0.99] transition-transform"
    >
      <div className="w-9 h-9 rounded-full bg-surface2 border border-line flex items-center justify-center shrink-0 overflow-hidden">
        {source.logo ? (
          <img src={source.logo} alt="" width={20} height={20} className="rounded-sm" />
        ) : (
          <span className="text-[13px] font-bold text-ink-dim">{source.domain[0]?.toUpperCase()}</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-[12px] text-ink-dim">
          <span className="truncate">{source.domain}</span>
          {source.ago && <><span>·</span><span className="shrink-0">{source.ago}</span></>}
        </div>
        <div className="text-[14.5px] font-semibold text-ink leading-snug mt-0.5 truncate">{source.title}</div>
        <div className="text-[12.5px] text-ink-dim leading-snug line-clamp-2">{source.snippet || "Open in the in-app browser"}</div>
      </div>
      <button
        aria-label="Bookmark"
        onClick={(e) => { e.stopPropagation(); onBookmark?.(); }}
        className={`w-8 h-8 -mr-1.5 rounded-full flex items-center justify-center shrink-0 ${bookmarked ? "text-accent" : "text-ink-dim"}`}
      >
        <Bookmark size={16} strokeWidth={1.8} fill={bookmarked ? "currentColor" : "none"} />
      </button>
    </div>
  );
}

export { faviconUrl };
