import { useEffect, useRef, useState } from "react";
import { ArrowUp, GraduationCap, Mic } from "lucide-react";
import { api, streamTurn } from "../lib/api";
import type { ChatMessage } from "../lib/api";

/** Private Chat — ephemeral: a real conversation that is HARD-DELETED on exit. */
export default function Private() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [value, setValue] = useState("");
  const [fast, setFast] = useState(true);
  const [busy, setBusy] = useState(false);
  const convRef = useRef<string>("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let dead = false;
    api.createConversation("Private chat").then((c) => { if (!dead) convRef.current = c.id; });
    return () => {
      dead = true;
      const id = convRef.current;
      if (id) void api.deleteConversation(id); // THE ERASE IS REAL — messages + conversation
    };
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    const text = value.trim();
    if (!text || busy || !convRef.current) return;
    setBusy(true);
    setValue("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    const reply: ChatMessage = { role: "assistant", content: "" };
    setMessages((m) => [...m, reply]);
    try {
      await streamTurn(convRef.current, text, "uncensored", (ev) => {
        if (ev.kind === "token") { reply.content += ev.delta; setMessages((m) => [...m]); }
        else if (ev.kind === "error") { reply.content += `\n⚠ ${ev.error}`; setMessages((m) => [...m]); }
      });
    } catch (err) {
      reply.content += `\n⚠ ${(err as Error).message}`;
      setMessages((m) => [...m]);
    } finally { setBusy(false); }
  };

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-[#F5F3FF] via-white to-[#EFF6FF]">
      <div className="flex-1 overflow-y-auto px-4 pt-6 pb-2">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
            <div className="relative">
              <GraduationCap size={52} strokeWidth={1} className="text-ink" />
              <div className="absolute left-1/2 top-[58%] -translate-x-1/2 flex gap-1">
                <span className="w-4 h-1.5 rounded-full bg-ink" />
                <span className="w-4 h-1.5 rounded-full bg-ink" />
              </div>
            </div>
            <h1 className="text-[20px] font-bold text-ink">Private Chat</h1>
            <p className="text-[13.5px] text-ink-dim px-8">This chat won&apos;t appear in history and will be fully erased</p>
          </div>
        ) : (
          <>
            {messages.map((m, i) => (
              <div key={i} className={`mb-4 max-w-[85%] ${m.role === "user" ? "ml-auto bg-ink text-white rounded-3xl rounded-br-lg px-4 py-2.5 text-[15.5px]" : "text-ink text-[15.5px] leading-relaxed whitespace-pre-wrap break-words"}`}>
                {m.content}
              </div>
            ))}
            {busy && <div className="text-[13px] text-ink-dim">thinking…</div>}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="px-4 pb-[calc(env(safe-area-inset-bottom)+12px)]">
        <div className="rounded-3xl bg-ink px-4 py-3 flex items-center gap-2 shadow-lift">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask Anything"
            className="flex-1 bg-transparent outline-none text-white text-[15.5px] placeholder:text-[#9CA3AF]"
          />
          <button onClick={() => setFast(!fast)}
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-semibold border transition-colors ${fast ? "border-white/40 text-white" : "border-white/20 text-white/50"}`}
            aria-pressed={fast}>Fast</button>
          <Mic size={19} className="text-white/70 shrink-0" />
          <button onClick={send} disabled={!value.trim() || busy}
            className="w-9 h-9 rounded-full bg-accent flex items-center justify-center disabled:bg-white/15 shrink-0 active:scale-95 transition-transform">
            <ArrowUp size={18} className="text-white" strokeWidth={2.4} />
          </button>
        </div>
      </div>
    </div>
  );
}
