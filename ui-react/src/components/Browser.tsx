import { useEffect, useRef, useState, useCallback } from "react";
import { ArrowLeft, ArrowRight, Maximize2, Minimize2, RotateCw, X, Lock, Globe, Mail } from "lucide-react";
import { useStore } from "../lib/store";

type WSMsg =
  | { type: "frame"; data: string }
  | { type: "url"; url: string }
  | { type: "error"; error: string };

const FW = 480;
const FH = 854;

/** In-app browser: the REAL page from the server's Chromium, streamed over an
 * authenticated WebSocket. Loads ANY url — Google, Discord, banking — and you
 * log in yourself, typing into the live site. Cookies persist server-side. */
export default function Browser() {
  const open = useStore((s) => s.browserOpen);
  const targetUrl = useStore((s) => s.browserUrl);
  const page = useStore((s) => s.browserPage);
  const closeBrowser = useStore((s) => s.closeBrowser);
  const openBrowser = useStore((s) => s.openBrowser);

  const [frame, setFrame] = useState<string>("");
  const [expanded, setExpanded] = useState(false);

  const [addr, setAddr] = useState("");
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const hiddenRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<{ down: boolean; moved: number }>({ down: false, moved: 0 });

  const send = useCallback((obj: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }, []);

  useEffect(() => {
    if (!open) return;
    setFrame("");
    setAddr(targetUrl.replace(/^https?:\/\//, ""));
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/browser/arena-login?url=${encodeURIComponent(targetUrl)}&page=${page}`);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as WSMsg;
      if (msg.type === "frame") setFrame(msg.data);
      else if (msg.type === "url") { setAddr(msg.url.replace(/^https?:\/\//, "")); }
    };
    ws.onclose = () => { setConnected(false); if (useStore.getState().browserOpen) closeBrowser(); };
    return () => { ws.close(); wsRef.current = null; };
  }, [open, targetUrl, page, closeBrowser]);

  // external open requests (source cards etc.)
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
    const img = imgRef.current!;
    const r = img.getBoundingClientRect();
    return {
      x: Math.round(((e.clientX - r.left) / r.width) * FW),
      y: Math.round(((e.clientY - r.top) / r.height) * FH),
    };
  };

  const gotoTyped = () => {
    const v = addr.trim();
    if (!v) return;
    const url = /^https?:\/\//.test(v) ? v : `https://${v}`;
    send({ type: "goto", url });
  };

  return (
    <div className="absolute inset-0 z-[100] bg-white flex flex-col">
      {/* chrome: back, forward, reload, url bar, close */}
      <div className="flex items-center gap-1 px-3 pt-[calc(env(safe-area-inset-top)+8px)] pb-2.5 border-b border-line bg-white">
        <button aria-label="Back" onClick={() => send({ type: "back" })} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface"><ArrowLeft size={19} className="text-ink" /></button>
        <button aria-label="Forward" onClick={() => send({ type: "forward" })} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface"><ArrowRight size={19} className="text-ink" /></button>
        <button aria-label="Reload" onClick={() => send({ type: "reload" })} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface"><RotateCw size={17} className="text-ink" /></button>
        <form onSubmit={(e) => { e.preventDefault(); gotoTyped(); }}
          className="flex-1 flex items-center gap-2 bg-surface rounded-full px-3.5 py-2 min-w-0">
          <Lock size={12} className="text-ink-dim shrink-0" />
          <input
            value={addr}
            onChange={(e) => setAddr(e.target.value)}
            className="flex-1 bg-transparent outline-none text-[13.5px] text-ink truncate min-w-0"
            placeholder="Search or enter address"
            enterKeyHint="go"
          />
          <span className={`w-2 h-2 rounded-full shrink-0 ${connected ? "bg-success" : "bg-line"}`} />
        </form>
        <button aria-label={expanded ? "Shrink" : "Expand"} onClick={() => setExpanded(!expanded)} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface">
          {expanded ? <Minimize2 size={17} className="text-ink" /> : <Maximize2 size={17} className="text-ink" />}
        </button>
        <button aria-label="Close" onClick={closeBrowser} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface"><X size={19} className="text-ink" /></button>
      </div>

      {/* which live tab we're watching: the arena page or the agent's own mail */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-line bg-surface2/50">
        {([["arena", "Arena", Globe], ["webmail", "Mail", Mail]] as const).map(([id, label, Icon]) => (
          <button key={id} onClick={() => openBrowser(id === "arena" ? targetUrl : "https://mail.google.com", id)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium transition-colors ${page === id ? "bg-white text-ink shadow-soft" : "text-ink-dim"}`}>
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {/* live viewport */}
      <div className="flex-1 relative bg-[#111] flex items-center justify-center overflow-hidden">
        {frame ? (
          <img
            ref={imgRef}
            src={`data:image/jpeg;base64,${frame}`}
            alt="Live web page"
            draggable={false}
            className={`select-none touch-none cursor-pointer ${expanded ? "w-full h-auto object-fill max-w-none" : "max-w-full max-h-full h-full object-contain"}`}
            onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; dragRef.current = { down: true, moved: 0 }; const c = coords(e); send({ type: "mousedown", ...c }); (e.target as HTMLElement).setPointerCapture(e.pointerId); }}
            onPointerMove={(e) => { const c = coords(e); if (dragRef.current.down) dragRef.current.moved += 1; send({ type: "mousemove", ...c }); }}
            onPointerUp={(e) => { if (!dragRef.current.down) return; dragRef.current.down = false; const c = coords(e); send({ type: "mouseup", ...c }); if (e.pointerType !== "mouse") send({ type: "click", ...c }); }}
            onWheel={(e) => { e.preventDefault(); send({ type: "scroll", dx: Math.round(e.deltaX), dy: Math.round(e.deltaY) }); }}
            onClick={() => hiddenRef.current?.focus()}
          />
        ) : (
          <div className="text-[14px] text-white/60 flex flex-col items-center gap-3">
            <div className="w-8 h-8 rounded-full border-2 border-white/20 border-t-white animate-spin" />
            Loading {page === "webmail" ? "the agent's mail" : targetUrl.replace(/^https?:\/\//, "")}…
          </div>
        )}
        {/* mobile keyboards: hidden input forwards keystrokes into the page */}
        <input
          ref={hiddenRef}
          className="absolute left-[-9999px] top-0 w-px h-px opacity-0 text-[16px]"
          autoCapitalize="off"
          autoComplete="off"
          spellCheck={false}
          onChange={() => { if (hiddenRef.current) hiddenRef.current.value = ""; }}
          onBeforeInput={(e) => {
            const native = e.nativeEvent as InputEvent;
            const t = e.target as HTMLInputElement;
            if (native.inputType === "insertText" && native.data) { send({ type: "type", text: native.data }); t.value = ""; }
            else if (native.inputType === "insertLineBreak") { send({ type: "key", key: "Enter" }); t.value = ""; }
            else if (native.inputType === "deleteContentBackward") send({ type: "key", key: "Backspace" });
          }}
          onKeyDown={(e) => { if (e.key === "Enter") { send({ type: "key", key: "Enter" }); } }}
        />
      </div>

      <div className="px-4 pb-[calc(env(safe-area-inset-bottom)+10px)] pt-2 bg-white border-t border-line flex items-center justify-between gap-3">
        <p className="text-[12px] text-ink-dim">It's the real site, live from the server's browser — log into anything, cookies persist.</p>
        <button onClick={closeBrowser} className="shrink-0 bg-ink text-white rounded-full px-4 py-2 text-[13px] font-semibold">Done</button>
      </div>
    </div>
  );
}
