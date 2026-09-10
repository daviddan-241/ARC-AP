import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BrainCircuit, Check, ChevronDown, ChevronRight, Loader2, Mic, Paperclip, Send, SlidersHorizontal, Sparkles } from "lucide-react";
import { Link } from "wouter";
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
  const [attachName, setAttachName] = useState<string | null>(null);
  const [attaching, setAttaching] = useState(false);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const streamRef = useRef(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking]);

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
    }
  };

  const showEmpty = messages.length === 0;

  return (
    <div className="arc-chat-page flex h-full min-h-0 flex-col">
      <div className="arc-chat-scroll flex-1 overflow-y-auto px-4 pt-6 sm:px-8">
        <div className="mx-auto max-w-3xl">
          {showEmpty ? (
            <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
              <div className="arc-gradient h-14 w-14 rounded-2xl opacity-90" />
              <h2 className="arc-title text-4xl font-bold sm:text-5xl">
                <span className="arc-gradient-text">Hello, Danny.</span>
              </h2>
              <p className="mt-2 text-sm text-slate-500">What should we make real today?</p>
            </div>
          ) : (
            <>
              {messages.map((m, i) => (
                <MessageBubble key={i} m={m} isLast={i === messages.length - 1} thinking={thinking}
                  steps={steps} sources={sources} />
              ))}
              {thinking && <div className="flex items-center gap-2 pb-3 text-[13px] text-slate-500"><Loader2 size={14} className="animate-spin" />Thinking…</div>}
            </>
          )}
          <div className="pb-3 pt-3">
            {!showEmpty && quickReplies.length > 0 && !thinking && (
              <div className="arc-no-scrollbar flex items-center gap-2 overflow-x-auto">
                {quickReplies.map((c) => (
                  <button key={c} onClick={() => { setText(c); textRef.current?.focus(); }} className="shrink-0 whitespace-nowrap rounded-full border border-cyan-300/20 bg-cyan-300/[.06] px-3.5 py-1.5 text-[12.5px] font-medium text-cyan-200 active:scale-95">{c}</button>
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
            <button key={c} onClick={() => { setText(c); textRef.current?.focus(); }} className="arc-card shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[12.5px] font-medium text-slate-300 hover:text-white active:scale-95">{c.length > 44 ? c.slice(0, 44) + "…" : c}</button>
          ))}
        </div>
      )}

      {/* the real composer — Fast/Deep maps to real backend moods */}
      <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-8">
        <div className="arc-composer rounded-2xl border border-white/[.11] bg-[#111531] p-2 shadow-2xl">
          <textarea ref={textRef} value={text} onChange={(e) => setText(e.target.value)} rows={1}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const v = text; setText(""); send(v); } }}
            placeholder="Ask anything. Make it real."
            className="arc-focus max-h-28 min-h-12 w-full resize-none bg-transparent px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600" />
          {attachName && <div className="mx-1 mb-1 inline-flex items-center gap-1.5 rounded-full bg-violet-400/10 px-3 py-1 text-[11.5px] text-violet-200"><Paperclip size={11} />{attachName}<button onClick={() => setAttachName(null)} className="text-slate-500 hover:text-white">×</button></div>}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-1">
              <button onClick={() => { setDeep(!deep); setMood(deep ? "uncensored" : "planner"); }}
                className={`arc-transition flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] ${deep ? "bg-violet-400/15 text-violet-200" : "bg-cyan-300/10 text-cyan-200"}`}>
                <SlidersHorizontal size={13} />{deep ? "Deep" : "Fast"}
              </button>
              <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f); e.target.value = ""; }} />
              <button onClick={() => fileRef.current?.click()} aria-label="Attach a file"
                className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 hover:bg-white/[.07] hover:text-white active:scale-95">
                {attaching ? <Loader2 size={15} className="animate-spin" /> : <Paperclip size={15} />}
              </button>
              <span className="hidden items-center gap-1 text-[11px] text-slate-600 sm:flex"><Sparkles size={11} />arena.ai session</span>
            </div>
            <button onClick={() => { const v = text; setText(""); send(v); }} disabled={!text.trim() || thinking}
              className="arc-transition flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 text-[#10132f] disabled:cursor-not-allowed disabled:opacity-30 hover:brightness-110 active:scale-95">
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
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
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-gradient-to-br from-cyan-300/90 to-violet-500/90 px-4 py-2.5 text-[14.5px] leading-relaxed font-medium text-[#10132f]">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 pb-1.5 text-[11px] text-slate-600"><BrainCircuit size={12} />ARC{m.model ? ` · ${m.model}` : ""}</div>
      <div className="whitespace-pre-wrap break-words text-[15px] leading-[1.65] text-slate-100">{m.content}</div>
      {hasThoughts && (
        <div className="mt-2.5">
          <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 py-1.5 text-[12.5px] font-medium text-slate-500 hover:text-white">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {steps.length > 0 ? steps[steps.length - 1].label : "Thinking"}
            {thinking && <Loader2 size={12} className="animate-spin" />}
          </button>
          <AnimatePresence initial={false}>
            {open && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
                <div className="arc-card mt-1.5 rounded-2xl p-4">
                  <p className="arc-mono mb-2 text-[10px] uppercase tracking-[.22em] text-cyan-300/70">Exploration progress</p>
                  {steps.map((st) => (
                    <div key={st.id} className="flex items-start gap-2 py-1">
                      {st.state === "ok" ? <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400/10"><Check size={12} strokeWidth={3} className="text-emerald-300" /></span>
                        : st.state === "running" ? <Loader2 size={16} className="mt-0.5 shrink-0 animate-spin text-slate-500" />
                        : <span className="h-5 w-5 shrink-0 rounded-full border-2 border-rose-400/40" />}
                      <div className="text-[13px] leading-snug text-slate-300">{st.label}{st.detail && <span className="text-slate-600"> — {st.detail.slice(0, 140)}</span>}</div>
                    </div>
                  ))}
                  {sources.length > 0 && (
                    <>
                      <p className="arc-mono mb-1 mt-4 text-[10px] uppercase tracking-[.22em] text-cyan-300/70">Sources</p>
                      <div className="grid gap-1.5">
                        {sources.slice(0, 6).map((src, i) => (
                          <a key={i} href={src.url} target="_blank" rel="noreferrer" className="flex items-center gap-2.5 rounded-xl border border-white/[.07] bg-white/[.03] p-2.5 hover:border-cyan-300/30">
                            {src.logo ? <img src={src.logo} alt="" className="h-6 w-6 rounded-md" /> : <div className="arc-gradient h-6 w-6 rounded-md" />}
                            <span className="min-w-0 flex-1"><b className="block truncate text-[12.5px] text-white">{src.title}</b><small className="text-[11px] text-slate-600">{src.domain}</small></span>
                          </a>
                        ))}
                      </div>
                    </>
                  )}
                  <Link href="/thoughts" className="mt-3 inline-block text-[12.5px] font-semibold text-cyan-300">Open full Thoughts →</Link>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
