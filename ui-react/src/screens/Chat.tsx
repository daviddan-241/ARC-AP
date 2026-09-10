import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Check, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, streamTurn } from "../lib/api";
import type { ChatMessage } from "../lib/api";
import { useStore, faviconUrl } from "../lib/store";
import ChatInput from "../components/ChatInput";
import SourceCard from "../components/SourceCard";

const DEFAULT_CHIPS = [
  "List every tool you have and what each does, then run one to prove it.",
  "Check the system you're running on: OS, RAM, disk, network.",
  "Open a browser, go to a news site and summarize today's top stories.",
];

function MessageBubble({ m, isLast }: { m: ChatMessage; isLast: boolean }) {
  const sources = useStore((s) => s.sources);
  const steps = useStore((s) => s.steps);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const hasThoughts = isLast && m.role === "assistant" && (steps.length > 0 || sources.length > 0);

  if (m.role === "user") {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[85%] bg-accent text-white rounded-3xl rounded-br-lg px-4 py-2.5 text-[15.5px] leading-relaxed whitespace-pre-wrap break-words">
          {m.content}
        </div>
      </div>
    );
  }
  return (
    <div className="mb-5">
      <div className="max-w-full text-[15.5px] leading-[1.65] text-ink whitespace-pre-wrap break-words">{m.content}</div>
      {hasThoughts && (
        <div className="mt-2.5">
          <AnimatePresence initial={false}>
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25, ease: [0.2, 0.7, 0.2, 1] }} className="overflow-hidden">
              <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink-dim hover:text-ink py-1.5">
                {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                {steps.length > 0 ? steps[steps.length - 1].label : "Thinking"}
              </button>
              {open && (
                <div className="rounded-card bg-surface p-4 mt-1.5">
                  <div className="section-label mb-2">EXPLORATION PROGRESS</div>
                  {steps.map((st) => (
                    <div key={st.id} className="flex items-start gap-2 py-1">
                      {st.state === "ok" ? (
                        <span className="w-5 h-5 rounded-full bg-[#22C55E]/10 flex items-center justify-center shrink-0"><Check size={12} strokeWidth={3} className="text-success" /></span>
                      ) : st.state === "running" ? (
                        <Loader2 size={16} className="text-ink-dim animate-spin shrink-0 mt-0.5" />
                      ) : (
                        <span className="w-5 h-5 rounded-full border-2 border-line shrink-0" />
                      )}
                      <div className="text-[13.5px] text-ink leading-snug">
                        {st.label}
                        {st.detail && <span className="text-ink-dim"> — {st.detail.slice(0, 140)}</span>}
                      </div>
                    </div>
                  ))}
                  {sources.length > 0 && (
                    <>
                      <div className="section-label mt-4 mb-1">SEARCH RESULTS</div>
                      <div className="-mx-1">
                        {sources.slice(0, 6).map((src, i) => <SourceCard key={i} source={src} />)}
                      </div>
                    </>
                  )}
                  <button onClick={() => navigate("/thoughts")} className="mt-3 text-[13px] font-semibold text-accent">Open full Thoughts →</button>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

export default function Chat() {
  const conversationId = useStore((s) => s.conversationId);
  const setConversation = useStore((s) => s.setConversation);
  const messages = useStore((s) => s.messages);
  const addMessage = useStore((s) => s.addMessage);
  const thinking = useStore((s) => s.thinking);
  const setThinking = useStore((s) => s.setThinking);
  const mood = useStore((s) => s.mood);
  const clearThoughts = useStore((s) => s.clearThoughts);
  const addStep = useStore((s) => s.addStep);
  const resolveStep = useStore((s) => s.resolveStep);
  const addSources = useStore((s) => s.addSources);
  const quickReplies = useStore((s) => s.quickReplies);
  const setQuickReplies = useStore((s) => s.setQuickReplies);
  const [chips, setChips] = useState<string[]>(DEFAULT_CHIPS);
  const streamRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // load history for the active conversation (real messages from the API)
  useEffect(() => {
    let alive = true;
    if (!conversationId) { clearThoughts(); return; }
    (async () => {
      try {
        const msgs = await api.messages(conversationId);
        if (!alive) return;
        useStore.setState({ messages: msgs });
        setChips([]);
      } catch { /* unauthenticated — App gate handles it */ }
    })();
    return () => { alive = false; };
  }, [conversationId, clearThoughts]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (text: string) => {
    const body = text.trim();
    if (!body || streamRef.current) return;
    streamRef.current = true;
    setThinking(true);
    setQuickReplies([]);
    clearThoughts();
    addMessage({ role: "user", content: body });
    let convId = conversationId;
    if (!convId) {
      convId = (await api.createConversation(body.slice(0, 40) || "New chat")).id;
      setConversation(convId);
    }
    const reply: ChatMessage = { role: "assistant", content: "" };
    addMessage(reply);
    let openStep: string | null = null;
    try {
      await streamTurn(convId!, body, mood, (ev) => {
        if (ev.kind === "token") {
          reply.content += ev.delta;
          useStore.setState((s) => ({ messages: [...s.messages] }));
        } else if (ev.kind === "tool_call") {
          openStep = addStep(`Running ${ev.tool}`, JSON.stringify(ev.args ?? {}).slice(0, 140));
          // real search results become tappable source cards
          const args = ev.args ?? {};
          const url = (args.url as string) || (args.query as string);
          if (typeof url === "string" && /^https?:\/\//.test(url)) {
            try { const u = new URL(url); addSources([{ url, domain: u.hostname.replace(/^www\./, ""), title: ev.tool, snippet: String(args.query ?? ""), logo: faviconUrl(u.hostname) }]); } catch { /* skip */ }
          }
        } else if (ev.kind === "tool_result") {
          if (openStep) resolveStep(openStep, ev.ok, ev.ok ? (ev.output ?? "done").slice(0, 160) : `⚠ ${ev.error ?? "failed"}`);
          openStep = null;
          // parse search-style tool output into source cards when it's a list of urls
          const out = ev.output ?? "";
          const urls = out.match(/https?:\/\/[^\s"'<>)]+/g);
          if (urls && ev.ok) {
            const seen = new Set<string>();
            const srcs = urls.slice(0, 6).filter((u) => (seen.has(u) ? false : seen.add(u) && true)).map((u) => {
              let title = "Result", snippet = "";
              try {
                const host = new URL(u).hostname.replace(/^www\./, "");
                const m = out.match(new RegExp(u.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").slice(0, 60) + "[^\\n]*?([^\\n]{10,140})"));
                if (m) snippet = m[1].trim();
                title = host;
                return { url: u, domain: host, title, snippet, logo: faviconUrl(host) };
              } catch { return { url: u, domain: u, title, snippet }; }
            });
            addSources(srcs);
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
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto px-4 pt-2">
        {showEmpty ? (
          <div className="h-full flex flex-col items-center justify-center gap-1 pb-6">
            <h2 className="text-[26px] font-bold tracking-tight bg-gradient-to-r from-ink via-[#7c5cff] to-accent bg-clip-text text-transparent">Hello, Danny</h2>
            <p className="text-[15px] text-ink-dim">What can I do for you?</p>
          </div>
        ) : (
          <>
            {messages.map((m, i) => <MessageBubble key={i} m={m} isLast={i === messages.length - 1} />)}
            {thinking && <div ref={bottomRef} className="flex items-center gap-2 text-[13px] text-ink-dim pb-2"><Loader2 size={14} className="animate-spin" />Thinking…</div>}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* suggestion chips — pills under the last message / greeting */}
      {chips.length > 0 && !thinking && (
        <div className="px-4 pb-2 flex gap-2 overflow-x-auto no-scrollbar">
          {chips.map((c) => (
            <button key={c} onClick={() => send(c)}
              className="shrink-0 border border-line rounded-full px-3.5 py-2 text-[13px] font-medium text-ink hover:bg-surface active:scale-95 transition-all">
              {c.length > 44 ? c.slice(0, 44) + "…" : c}
            </button>
          ))}
        </div>
      )}
      {quickReplies.length > 0 && !thinking && (
        <div className="px-4 pb-2 flex gap-2 overflow-x-auto no-scrollbar">
          {quickReplies.map((c) => (
            <button key={c} onClick={() => send(c)}
              className="shrink-0 bg-accent/8 border border-accent/25 rounded-full px-3.5 py-2 text-[13px] font-medium text-accent active:scale-95 transition-all">
              {c}
            </button>
          ))}
        </div>
      )}

      <ChatInput onSend={send} />
    </div>
  );
}
