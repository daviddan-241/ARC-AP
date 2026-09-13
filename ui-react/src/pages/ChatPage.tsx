import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowDown, BrainCircuit, Check, ChevronDown, ChevronRight, Loader2, Mic, Paperclip, PlugZap, Plus, Send, SlidersHorizontal, Sparkles, X, Zap } from "lucide-react";
import { Link, useLocation } from "wouter";
import { api, streamTurn, uploadsProjectId } from "../lib/api";
import type { ChatMessage } from "../lib/api";
import { faviconUrl, useStore } from "../lib/store";

const CHIPS = [
  "List every tool you have and what each does, then run one to prove it.",
  "Check the system you're running on: OS, RAM, disk, network.",
  "Open a browser, go to a news site and summarize today's top stories.",
];

/** The real chat: SSE-streamed agent turns from the live backend, with the
 * live thoughts panel and real source cards. No anonymous mock — every
 * message runs the real agent loop through arena.ai. */
export default function ChatPage() {
  const conversationId = useStore((s) => s.conversationId);
  const setConversation = useStore((s) => s.setConversation);
  const messages = useStore((s) => s.messages);
  const addMessage = useStore((s) => s.addMessage);
  const thinking = useStore((s) => s.thinking);
  const setThinking = useStore((s) => s.setThinking);
  const mood = useStore((s) => s.mood);
  const setMood = useStore((s) => s.setMood);
  const steps = useStore((s) => s.steps);
  const sources = useStore((s) => s.sources);
  const clearThoughts = useStore((s) => s.clearThoughts);
  const addStep = useStore((s) => s.addStep);
  const resolveStep = useStore((s) => s.resolveStep);
  const addSources = useStore((s) => s.addSources);
  const openBrowser = useStore((s) => s.openBrowser);

  const [text, setText] = useState("");
  const [deep, setDeep] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const [attachName, setAttachName] = useState<string | null>(null);
  const [attaching, setAttaching] = useState(false);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const streamRef = useRef(false);
  const textRef = useRef<HTMLTextAreaElement>(null);

  // honest mic fallback: if this browser has no SpeechRecognition, SAY so
  // instead of a silent no-op tap — a button that does nothing invisibly is
  // exactly the kind of fake this app doesn't ship.
  const [micMsg, setMicMsg] = useState("");
  const micMsgTimer = useRef<number | null>(null);
  const showMicMsg = (msg: string) => {
    setMicMsg(msg);
    if (micMsgTimer.current) window.clearTimeout(micMsgTimer.current);
    micMsgTimer.current = window.setTimeout(() => setMicMsg(""), 2600);
  };
  const toggleMic = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      showMicMsg("Dictation isn't supported in this browser.");
      textRef.current?.focus();
      return;
    }
    if (listening) { recognitionRef.current?.stop(); return; }
    const rec = new SpeechRecognition();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    let base = text ? text + " " : "";
    rec.onresult = (e: any) => {
      let transcript = "";
      for (let i = 0; i < e.results.length; i++) transcript += e.results[i][0].transcript;
      setText(base + transcript);
    };
    rec.onend = () => setListening(false);
    rec.onerror = (e: any) => {
      setListening(false);
      const why: Record<string, string> = {
        "not-allowed": "Microphone permission was denied — enable it in your browser settings.",
        "service-not-allowed": "The browser blocked dictation services for this page.",
        "no-speech": "Didn't catch any speech — try again.",
        "audio-capture": "No microphone found on this device.",
      };
      showMicMsg(why[e?.error] ?? "Dictation failed — try again.");
    };
    recognitionRef.current = rec;
    setListening(true);
    rec.start();
  };
  useEffect(() => () => { if (micMsgTimer.current) window.clearTimeout(micMsgTimer.current); }, []);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // "Jump to latest" only shows when you've actually scrolled away from the
  // bottom -- and, just as importantly, we STOP force-scrolling you back down
  // once you've scrolled up on purpose. Real chat apps never yank your scroll
  // position out from under you.
  //
  // This used to be threshold math on the 'scroll' event combined with
  // `scrollIntoView({behavior:'smooth'})` re-fired on every streamed token.
  // The smooth animation can't be interrupted cleanly by a manual scroll
  // mid-flight, so every new token effectively restarted the fight and
  // snapped the view back down — "it keeps going to the end, doesn't stay
  // out". Fixed with the pattern real chat apps (Discord/Slack/ChatGPT) use:
  // an IntersectionObserver watching a sentinel div right after the last
  // message, plus an INSTANT (non-animated) follow-scroll while streaming,
  // so there's never an animation for a manual scroll to fight.
  const [atBottom, setAtBottom] = useState(true);
  const [connectCard, setConnectCard] = useState<{ connector: string; reason: string } | null>(null);
  const [, navigate] = useLocation();
  useEffect(() => {
    const el = scrollRef.current;
    const sentinel = bottomRef.current;
    if (!el || !sentinel) return;
    const io = new IntersectionObserver(
      ([entry]) => setAtBottom(entry.isIntersecting),
      { root: el, threshold: 0, rootMargin: "0px 0px 32px 0px" },
    );
    io.observe(sentinel);
    return () => io.disconnect();
  }, []);
  const scrollToBottom = (smooth = true) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setAtBottom(true);
  };

  useEffect(() => {
    if (!conversationId) { clearThoughts(); return; }
    let alive = true;
    (async () => {
      try {
        const msgs = await api.messages(conversationId);
        if (alive) useStore.setState({ messages: msgs });
      } catch { /* gate handles auth */ }
    })();
    return () => { alive = false; };
  }, [conversationId, clearThoughts]);

  useEffect(() => {
    // instant, not smooth: an ongoing animation is what fights a manual
    // scroll — an instant jump has nothing to fight, so a real scroll-up
    // always wins immediately, every time.
    if (atBottom) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "auto" });
  }, [messages, thinking, atBottom]);

  const attach = async (file: File) => {
    setAttaching(true);
    try {
      const pid = await uploadsProjectId();
      await api.uploadFile(pid, file);
      setAttachName(file.name);
    } catch { setAttachName(null); }
    finally { setAttaching(false); }
  };

  const send = async (raw: string) => {
    const body = raw.trim();
    if (!body || streamRef.current) return;
    streamRef.current = true;
    setThinking(true);
    setQuickReplies([]);
    clearThoughts();
    const full = attachName ? `${body}\n[attached file: ${attachName}]` : body;
    setAttachName(null);
    addMessage({ role: "user", content: full });
    let convId = conversationId;
    if (!convId) {
      convId = (await api.createConversation(body.slice(0, 40) || "New chat")).id;
      setConversation(convId);
    }
    const reply: ChatMessage = { role: "assistant", content: "" };
    addMessage(reply);
    let openStep: string | null = null;
    try {
      await streamTurn(convId, full, mood, (ev) => {
        if (ev.kind === "token") {
          reply.content += ev.delta;
          useStore.setState((s) => ({ messages: [...s.messages] }));
        } else if (ev.kind === "tool_call") {
          openStep = addStep(`Running ${ev.tool}`, JSON.stringify(ev.args ?? {}).slice(0, 140));
          const args = ev.args ?? {};
          const url = (args.url as string) || (args.query as string);
          if (typeof url === "string" && /^https?:\/\//.test(url)) {
            try {
              const u = new URL(url);
              addSources([{ url, domain: u.hostname.replace(/^www\./, ""), title: ev.tool, snippet: String(args.query ?? ""), logo: faviconUrl(u.hostname) }]);
            } catch { /* skip */ }
          }
        } else if (ev.kind === "tool_result") {
          if (openStep) resolveStep(openStep, ev.ok, ev.ok ? (ev.output ?? "done").slice(0, 160) : `⚠ ${ev.error ?? "failed"}`);
          openStep = null;
          const out = ev.output ?? "";
          const urls = ev.ok ? out.match(/https?:\/\/[^\s"'<>)]+/g) : null;
          if (urls) {
            const seen = new Set<string>();
            addSources(urls.slice(0, 6).filter((u) => (seen.has(u) ? false : seen.add(u) && true)).map((u) => {
              try {
                const host = new URL(u).hostname.replace(/^www\./, "");
                return { url: u, domain: host, title: host, snippet: "", logo: faviconUrl(host) };
              } catch { return { url: u, domain: u, title: "Result", snippet: "" }; }
            }));
          }
        } else if (ev.kind === "learned") {
          addStep(`Remembered: ${ev.key ?? "memory"}`, ev.content.slice(0, 140));
        } else if (ev.kind === "done") {
          reply.model = ev.model ?? null;
          useStore.setState((s) => ({ messages: [...s.messages] }));
          setQuickReplies(["What can you do next?", "Show me the files you touched", "Run another tool"]);
        } else if (ev.kind === "connect_required") {
          // real backend signal: a tool just failed because its connector
          // isn't set up — surface the right connect card automatically.
          setConnectCard({ connector: String(ev.connector ?? ""), reason: String(ev.reason ?? "") });
        } else if (ev.kind === "error") {
          if (openStep) resolveStep(openStep, false, ev.error);
          reply.content += `\n⚠ ${ev.error}`;
          useStore.setState((s) => ({ messages: [...s.messages] }));
        }
      });
    } catch (err) {
      addMessage({ role: "assistant", content: `⚠ ${(err as Error).message}` });
    } finally {
      streamRef.current = false;
      setThinking(false);
      // Voice setting (Settings → General → Voice, real browser speechSynthesis):
      // read the finished answer aloud when the operator turned it on.
      if (localStorage.getItem("arcReadAloud") === "1" && typeof speechSynthesis !== "undefined" && reply.content.trim()) {
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(reply.content.slice(0, 1200));
        u.rate = 1.02;
        speechSynthesis.speak(u);
      }
    }
  };

  const showEmpty = messages.length === 0;

  return (
    <div className="arc-chat-page relative flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="arc-chat-scroll flex-1 overflow-y-auto px-4 pt-6 sm:px-8">
        <div className="mx-auto max-w-3xl">
          {showEmpty ? (
            <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
              <div className="arc-gradient h-14 w-14 rounded-2xl opacity-90" />
              <h2 className="arc-title text-4xl font-bold sm:text-5xl">
                <span className="arc-gradient-text">Hello, Danny.</span>
              </h2>
              <p className="mt-2 text-sm text-[#6B7280]">What should we make real today?</p>
            </div>
          ) : (
            <>
              {messages.map((m, i) => (
                <MessageBubble key={i} m={m} isLast={i === messages.length - 1} thinking={thinking}
                  steps={steps} sources={sources} />
              ))}
              {thinking && <div className="flex items-center gap-2 pb-3 text-[13px] text-[#6B7280]"><Loader2 size={14} className="animate-spin" />Thinking…</div>}
            </>
          )}
          <div className="pb-3 pt-3">
            {!showEmpty && quickReplies.length > 0 && !thinking && (
              <div className="arc-no-scrollbar flex items-center gap-2 overflow-x-auto">
                {quickReplies.map((c) => (
                  <button key={c} onClick={() => { setText(c); textRef.current?.focus(); }} className="shrink-0 whitespace-nowrap rounded-full border border-[#6366F1]/30 bg-[#6366F1]/[.06] px-3.5 py-1.5 text-[12.5px] font-medium text-[#6366F1] active:scale-95">{c}</button>
                ))}
              </div>
            )}
          </div>
          <div ref={bottomRef} />
        </div>
      </div>

      {showEmpty && !thinking && (
        <div className="arc-no-scrollbar mx-auto flex w-full max-w-3xl items-center gap-2 overflow-x-auto px-4 pb-3 sm:px-8">
          {CHIPS.map((c) => (
            <button key={c} onClick={() => { setText(c); textRef.current?.focus(); }} className="arc-card shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[12.5px] font-medium text-[#374151] hover:text-[#111827] active:scale-95">{c.length > 44 ? c.slice(0, 44) + "…" : c}</button>
          ))}
        </div>
      )}

      {/* small floating "jump to latest" button — only visible once you've
         actually scrolled away from the bottom, per the reference shot.
         Sits just above the composer, centered, fades in/out. */}
      <AnimatePresence>
        {!atBottom && !showEmpty && (
          <motion.button
            key="jump-to-bottom"
            initial={{ opacity: 0, y: 8, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: 8, x: "-50%" }}
            onClick={() => scrollToBottom(true)}
            aria-label="Jump to latest message"
            className="arc-jump-btn absolute bottom-[6.5rem] left-1/2 z-20 flex h-9 w-9 items-center justify-center rounded-full border border-[#E5E7EB] bg-white text-[#1F2937] shadow-xl active:scale-95 sm:bottom-[6.75rem]">
            <ArrowDown size={16} />
          </motion.button>
        )}
      </AnimatePresence>

      {/* the real composer — a single Gemini-style pill: + / input / mic-or-send.
         Fast/Deep + attach live one tap away in the sheet below, so the main
         row stays exactly as clean as the reference shots. No outline ring —
         .arc-composer-pill:focus-within only shifts the border color. */}
      {/* auto-popup connect card — shown ONLY when the backend emitted a real
          connect_required event (a tool just failed for a missing connector). */}
      <AnimatePresence>
        {connectCard && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[90] flex items-end justify-center bg-black/40 p-4 backdrop-blur-sm sm:items-center"
            onClick={() => setConnectCard(null)}>
            <motion.div initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }}
              transition={{ type: "spring", damping: 28, stiffness: 300 }} onClick={(e) => e.stopPropagation()}
              className="arc-card w-full max-w-sm rounded-2xl p-5">
              <div className="mb-3 flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#6366F1]/10 text-[#6366F1]"><PlugZap size={18} /></span>
                <div>
                  <b className="block text-sm text-[#111827]">Connect {connectCard.connector === "arena" ? "Arena.ai" : connectCard.connector === "appdeploy" ? "AppDeploy" : "Composio"}</b>
                  <small className="text-xs text-[#6B7280]">{connectCard.reason}</small>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setConnectCard(null);
                    if (connectCard.connector === "arena") useStore.getState().openBrowser("https://arena.ai", "arena");
                    else navigate("/connections");
                  }}
                  className="flex-1 rounded-xl bg-[#6366F1] px-4 py-2.5 text-xs font-bold text-white active:scale-[.98]">
                  {connectCard.connector === "arena" ? "Sign in now" : "Open Plugins"}
                </button>
                <button onClick={() => setConnectCard(null)}
                  className="rounded-xl border border-[#E5E7EB] px-4 py-2.5 text-xs font-semibold text-[#374151]">
                  Later
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="arc-composer-dock mx-auto w-full max-w-3xl px-4 pb-4 sm:px-8">
        {attachName && (
          <div className="mb-2 flex justify-center">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-violet-400/10 px-3 py-1 text-[11.5px] text-violet-600">
              <Paperclip size={11} />{attachName}
              <button onClick={() => setAttachName(null)} aria-label="Remove attachment" className="text-[#6B7280] hover:text-[#111827]">×</button>
            </div>
          </div>
        )}
        {micMsg && (
          <p className="mb-1.5 text-center text-[11.5px] text-amber-600/90" role="status">{micMsg}</p>
        )}
        <div className="arc-composer-pill flex items-end gap-1 rounded-full border border-transparent bg-[#F3F4F6] p-1.5 shadow-sm">
          <button onClick={() => setSheetOpen(true)} aria-label="More options"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827] active:scale-95">
            <Plus size={19} />
          </button>
          <textarea ref={textRef} value={text} onChange={(e) => setText(e.target.value)} rows={1}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const v = text; setText(""); send(v); } }}
            placeholder="Ask anything. Make it real."
            className="max-h-28 min-h-10 w-full resize-none bg-transparent px-1 py-2 text-[15px] leading-6 text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
          {text.trim() ? (
            <button onClick={() => { const v = text; setText(""); send(v); }} disabled={thinking} aria-label="Send"
              className="arc-transition flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#6366F1] text-white disabled:cursor-not-allowed disabled:opacity-30 hover:brightness-110 active:scale-95">
              <Send size={17} />
            </button>
          ) : (
            <button onClick={toggleMic} aria-label={listening ? "Stop dictation" : "Dictate"}
              className={`arc-transition flex h-10 w-10 shrink-0 items-center justify-center rounded-full active:scale-95 ${listening ? "bg-rose-400/20 text-rose-600" : "text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"}`}>
              <Mic size={18} />
            </button>
          )}
        </div>
      </div>

      {/* the "+" sheet: mode toggle + attach — one tap away, keeps the main pill clean */}
      <AnimatePresence>
        {sheetOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSheetOpen(false)}
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm">
            <motion.div initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
              onClick={(e) => e.stopPropagation()} transition={{ type: "spring", damping: 28, stiffness: 300 }}
              className="arc-card w-full max-w-xl rounded-t-3xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:rounded-3xl">
              <div className="mb-4 flex items-center justify-between">
                <b className="text-sm font-semibold text-[#111827]">Composer options</b>
                <button onClick={() => setSheetOpen(false)} aria-label="Close" className="flex h-9 w-9 items-center justify-center rounded-xl text-[#6B7280] hover:bg-black/[.05] hover:text-[#111827]"><X size={17} /></button>
              </div>
              <p className="arc-mono mb-2 text-[10px] uppercase tracking-[.2em] text-[#6366F1]/70">Response mode</p>
              <div className="mb-5 grid grid-cols-2 gap-2">
                {([[false, "Fast", SlidersHorizontal, "Direct and quick"], [true, "Deep", Zap, "Thorough, more autonomous"]] as const).map(([isDeep, label, Icon, sub]) => (
                  <button key={label} onClick={() => { setDeep(isDeep); setMood(isDeep ? "high_autonomy" : "uncensored"); }}
                    className={`rounded-2xl border p-3 text-left ${deep === isDeep ? "border-[#6366F1]/50 bg-[#6366F1]/10" : "border-[#E5E7EB] hover:hover:border-[#6366F1]/40"}`}>
                    <span className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold text-[#111827]"><Icon size={14} className={deep === isDeep ? "text-[#6366F1]" : "text-[#6B7280]"} />{label}</span>
                    <small className="block text-[11px] text-[#6B7280]">{sub}</small>
                  </button>
                ))}
              </div>
              <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f); e.target.value = ""; setSheetOpen(false); }} />
              <button onClick={() => fileRef.current?.click()}
                className="flex w-full items-center gap-3 rounded-2xl border border-[#E5E7EB] p-3.5 text-left hover:hover:border-[#6366F1]/40">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-400/10 text-violet-600">
                  {attaching ? <Loader2 size={15} className="animate-spin" /> : <Paperclip size={15} />}
                </span>
                <span className="text-[13px] font-medium text-[#111827]">{attachName ? `Replace "${attachName}"` : "Attach a file"}</span>
              </button>
              <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-[#9CA3AF]"><Sparkles size={11} />Running on the live arena.ai session — full unrestricted access</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MessageBubble({ m, isLast, thinking, steps, sources }: {
  m: ChatMessage; isLast: boolean; thinking: boolean;
  steps: ReturnType<typeof useStore.getState>["steps"];
  sources: ReturnType<typeof useStore.getState>["sources"];
}) {
  const [open, setOpen] = useState(false);
  const hasThoughts = isLast && m.role === "assistant" && (steps.length > 0 || sources.length > 0);

  if (m.role === "user") {
    return (
      <div className="mb-5 flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-[#6366F1] px-4 py-2.5 text-[14.5px] leading-relaxed font-medium text-white">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 pb-1.5 text-[11px] text-[#9CA3AF]"><BrainCircuit size={12} />ARC{m.model ? ` · ${m.model}` : ""}</div>
      <div className="whitespace-pre-wrap break-words text-[15px] leading-[1.65] text-[#111827]">{m.content}</div>
      {hasThoughts && (
        <div className="mt-2.5">
          <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 py-1.5 text-[12.5px] font-medium text-[#6B7280] hover:text-[#111827]">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {steps.length > 0 ? steps[steps.length - 1].label : "Thinking"}
            {thinking && <Loader2 size={12} className="animate-spin" />}
          </button>
          <AnimatePresence initial={false}>
            {open && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
                <div className="arc-card mt-1.5 rounded-2xl p-4">
                  <p className="arc-mono mb-2 text-[10px] uppercase tracking-[.22em] text-[#6366F1]/70">Exploration progress</p>
                  {steps.map((st) => (
                    <div key={st.id} className="flex items-start gap-2 py-1">
                      {st.state === "ok" ? <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400/10"><Check size={12} strokeWidth={3} className="text-emerald-600" /></span>
                        : st.state === "running" ? <Loader2 size={16} className="mt-0.5 shrink-0 animate-spin text-[#6B7280]" />
                        : <span className="h-5 w-5 shrink-0 rounded-full border-2 border-rose-400/40" />}
                      <div className="text-[13px] leading-snug text-[#374151]">{st.label}{st.detail && <span className="text-[#9CA3AF]"> — {st.detail.slice(0, 140)}</span>}</div>
                    </div>
                  ))}
                  {sources.length > 0 && (
                    <>
                      <p className="arc-mono mb-1 mt-4 text-[10px] uppercase tracking-[.22em] text-[#6366F1]/70">Sources</p>
                      <div className="grid gap-1.5">
                        {sources.slice(0, 6).map((src, i) => (
                          <a key={i} href={src.url} target="_blank" rel="noreferrer" className="flex items-center gap-2.5 rounded-xl border border-[#E5E7EB] bg-black/[.03] p-2.5 hover:border-[#6366F1]/40">
                            {src.logo ? <img src={src.logo} alt="" className="h-6 w-6 rounded-md" /> : <div className="arc-gradient h-6 w-6 rounded-md" />}
                            <span className="min-w-0 flex-1"><b className="block truncate text-[12.5px] text-[#111827]">{src.title}</b><small className="text-[11px] text-[#9CA3AF]">{src.domain}</small></span>
                          </a>
                        ))}
                      </div>
                    </>
                  )}
                  <Link href="/thoughts" className="mt-3 inline-block text-[12.5px] font-semibold text-[#6366F1]">Open full Thoughts →</Link>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
