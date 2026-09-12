import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Compass, Globe, Lock, Mail, Maximize2, Minimize2, RotateCw, X } from "lucide-react";
import { useStore } from "../lib/store";

type WSMsg =
  | { type: "frame"; data: string }
  | { type: "url"; url: string }
  | { type: "error"; error: string };

const FW = 480;
const FH = 854;

/** The REAL server-side Chromium page, streamed as JPEG frames over an
 * authenticated WebSocket, with full input relay. You log into arena.ai or
 * your email here yourself — cookies persist in the server profile, so this
 * IS the login. Works as a full-screen overlay from anywhere in the app. */
export default function BrowserOverlay() {
  const open = useStore((s) => s.browserOpen);
  const targetUrl = useStore((s) => s.browserUrl);
  const page = useStore((s) => s.browserPage);
  const closeBrowser = useStore((s) => s.closeBrowser);
  const openBrowser = useStore((s) => s.openBrowser);

  const [frame, setFrame] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [addr, setAddr] = useState("");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const hiddenRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef({ down: false, moved: 0 });

  const send = useCallback((obj: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }, []);

  useEffect(() => {
    if (!open) return;
    setFrame(""); setError(""); setConnected(false);
    setAddr(targetUrl.replace(/^https?:\/\//, ""));
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${proto}//${location.host}/ws/browser/arena-login?url=${encodeURIComponent(targetUrl)}&page=${page}`);
    wsRef.current = ws;

    let gotFrame = false;
    const watchdog = window.setTimeout(() => {
      if (!gotFrame) setError(
        "The server browser isn't responding yet. On a cold instance the first launch can take up to a minute — retry below, and if it persists check that ARENA_TRANSPORT=web is set and the instance has RAM headroom for Chromium.");
    }, 45_000);

    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as WSMsg;
      if (msg.type === "frame") { gotFrame = true; setError(""); setFrame(msg.data); }
      else if (msg.type === "url") setAddr(msg.url.replace(/^https?:\/\//, ""));
      else if (msg.type === "error") setError(msg.error);
    };
    ws.onclose = (e) => {
      window.clearTimeout(watchdog);
      setConnected(false);
      if (e.code === 4503 && useStore.getState().browserOpen)
        setError("Browser transport isn't running on the server (ARENA_TRANSPORT must be 'web' and Chromium installed). Automated chat still works.");
      else if (e.code === 4401 && useStore.getState().browserOpen)
        setError("Session expired — log in again, then reopen the browser.");
      else if (!gotFrame && useStore.getState().browserOpen)
        setError("The browser connection closed before the page loaded. Try again in a moment (cold start).");
    };
    return () => { window.clearTimeout(watchdog); ws.close(); wsRef.current = null; };
  }, [open, targetUrl, page]);

  useEffect(() => {
    const handler = (e: Event) => {
      const url = (e as CustomEvent<string>).detail;
      if (url) useStore.getState().openBrowser(url);
    };
    window.addEventListener("open-browser", handler);
    return () => window.removeEventListener("open-browser", handler);
  }, []);

  if (!open) return null;

  const coords = (e: React.PointerEvent) => {
    const r = imgRef.current!.getBoundingClientRect();
    return {
      x: Math.round(((e.clientX - r.left) / r.width) * FW),
      y: Math.round(((e.clientY - r.top) / r.height) * FH),
    };
  };

  const gotoTyped = () => {
    const v = addr.trim();
    if (!v) return;
    const url = /^https?:\/\//.test(v) ? v : `https://${v}`;
    // Never steer the arena/mail session pages away by typing â typed URLs
    // open the free persistent browsing session instead.
    if (page === "free") send({ type: "goto", url });
    else openBrowser(url, "free");
  };

  return (
    <div className="fixed inset-0 z-[100] flex flex-col bg-[#111827]">
      <div className="flex items-center gap-1 border-b border-[#E5E7EB] bg-[#F9FAFB]/90 px-3 py-2.5">
        <button aria-label="Back" onClick={() => send({ type: "back" })} className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"><ArrowLeft size={19} /></button>
        <button aria-label="Forward" onClick={() => send({ type: "forward" })} className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"><ArrowRight size={19} /></button>
        <button aria-label="Reload" onClick={() => send({ type: "reload" })} className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"><RotateCw size={16} /></button>
        <form onSubmit={(e) => { e.preventDefault(); gotoTyped(); }} className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-[#E5E7EB] bg-black/[.04] px-3 py-2">
          <Lock size={12} className="shrink-0 text-[#6B7280]" />
          <input value={addr} onChange={(e) => setAddr(e.target.value)} enterKeyHint="go"
            className="min-w-0 flex-1 truncate bg-transparent text-[13px] text-[#111827] outline-none placeholder:text-[#9CA3AF]"
            placeholder="Search or enter address" />
          <span className={`h-2 w-2 shrink-0 rounded-full ${connected ? "bg-emerald-400" : "bg-slate-700"}`} />
        </form>
        <button aria-label={expanded ? "Shrink" : "Expand"} onClick={() => setExpanded(!expanded)} className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]">
          {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
        </button>
        <button aria-label="Close" onClick={closeBrowser} className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"><X size={19} /></button>
      </div>

      {/* live tab selector: the arena page or the agent's own mail — both are real server tabs */}
      <div className="flex items-center gap-1 border-b border-[#E5E7EB] bg-white/60 px-3 py-1.5">
        {([["arena", "Arena", Globe, "https://arena.ai"], ["webmail", "Mail", Mail, "https://mail.google.com"], ["free", "Web", Compass, "https://www.google.com"]] as const).map(([id, label, Icon, url]) => (
          <button key={id} onClick={() => openBrowser(url, id)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors ${page === id ? "bg-black/[.06] text-[#111827]" : "text-[#6B7280] hover:text-[#111827]"}`}>
            <Icon size={13} />{label}
          </button>
        ))}
      </div>

      <div className="relative flex flex-1 items-center justify-center overflow-hidden bg-[#111827]">
        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-[#111827]/95 px-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-400/10 text-xl">⚠️</div>
            <p className="max-w-sm text-[14px] leading-relaxed text-[#374151]">{error}</p>
            <div className="flex gap-2">
              <button onClick={() => { setError(""); const u = targetUrl; useStore.getState().closeBrowser(); setTimeout(() => useStore.getState().openBrowser(u), 50); }
              } className="rounded-full bg-[#007AFF] px-5 py-2.5 text-[13px] font-bold text-white active:scale-95">Retry</button>
              <button onClick={closeBrowser} className="rounded-full border border-[#E5E7EB] px-5 py-2.5 text-[13px] font-semibold text-[#374151] hover:text-[#111827]">Close</button>
            </div>
          </div>
        )}
        {frame ? (
          <img ref={imgRef} src={`data:image/jpeg;base64,${frame}`} alt="Live web page" draggable={false}
            className={`select-none touch-none cursor-pointer ${expanded ? "h-auto w-full max-w-none object-fill" : "max-h-full max-w-full object-contain"}`}
            onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; dragRef.current = { down: true, moved: 0 }; const c = coords(e); send({ type: "mousedown", ...c }); (e.target as HTMLElement).setPointerCapture(e.pointerId); }}
            onPointerMove={(e) => { const c = coords(e); if (dragRef.current.down) dragRef.current.moved += 1; send({ type: "mousemove", ...c }); }}
            onPointerUp={(e) => { if (!dragRef.current.down) return; dragRef.current.down = false; const c = coords(e); send({ type: "mouseup", ...c }); if (e.pointerType !== "mouse") send({ type: "click", ...c }); }}
            onWheel={(e) => { e.preventDefault(); send({ type: "scroll", dx: Math.round(e.deltaX), dy: Math.round(e.deltaY) }); }}
            onClick={() => hiddenRef.current?.focus()} />
        ) : (
          !error && <div className="flex flex-col items-center gap-3 text-[14px] text-[#6B7280]">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-cyan-300" />
            Loading {page === "webmail" ? "the agent's mail" : targetUrl.replace(/^https?:\/\//, "")}…
          </div>
        )}
        {/* mobile keyboards: hidden input forwards keystrokes into the page */}
        <input ref={hiddenRef} className="absolute h-px w-px opacity-0" autoComplete="off" autoCapitalize="off"
          onChange={(e) => { for (const ch of e.target.value) send({ type: "key", key: ch }); e.target.value = ""; }}
          onKeyDown={(e) => {
            if (e.key === "Enter") send({ type: "key", key: "Enter" });
            else if (e.key === "Backspace") send({ type: "key", key: "Backspace" });
          }} />
      </div>
    </div>
  );
}
