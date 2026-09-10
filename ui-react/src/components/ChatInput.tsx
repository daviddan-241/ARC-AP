import { useEffect, useRef, useState } from "react";
import { ArrowUp, Mic, Plus, X } from "lucide-react";
import { api, uploadsProjectId } from "../lib/api";

/** Minimal Web Speech API types (not in the TS DOM lib for all targets). */
interface SRResult { 0: { transcript: string }; length: number }
interface SRLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((e: { results: { [i: number]: SRResult } & { length: number } }) => void) | null;
  start(): void;
  stop(): void;
}
type SRWindow = { SpeechRecognition?: new () => SRLike; webkitSpeechRecognition?: new () => SRLike };

/** Bottom input bar: attach (real upload), Fast toggle, voice (Web Speech API), send. */
export default function ChatInput({ onSend }: { onSend: (text: string) => void }) {
  const [value, setValue] = useState("");
  const [fast, setFast] = useState(true);
  const [listening, setListening] = useState(false);
  const [uploads, setUploads] = useState<string[]>([]);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const recRef = useRef<SRLike | null>(null);

  // keyboard stays glued to the bar (iOS Safari + Android)
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const onResize = () => {
      const gap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      const el = document.getElementById("kb-dock");
      if (el) el.style.paddingBottom = gap > 0 ? `${gap + 8}px` : "";
    };
    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, []);

  const autoGrow = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 132) + "px";
  };

  const send = () => {
    const text = value.trim();
    if (!text) return;
    let final = text;
    if (uploads.length) final += `\n\n[attached files in workspace Uploads: ${uploads.join(", ")}]`;
    setUploads([]);
    setValue("");
    requestAnimationFrame(autoGrow);
    onSend(final);
  };

  const toggleMic = () => {
    const w = window as unknown as SRWindow;
    const SR = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!SR) return;
    if (listening) { recRef.current?.stop(); return; }
    const rec = new SR();
    recRef.current = rec;
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      setValue(text);
      requestAnimationFrame(autoGrow);
    };
    rec.start();
  };

  const pickFile = async (file: File) => {
    try {
      const pid = await uploadsProjectId();
      await api.uploadFile(pid, file);
      setUploads((u) => [...u, file.name]);
    } catch {
      // real failure surfaced, not swallowed
      setValue((v) => v);
      alert("Upload failed");
    }
  };

  return (
    <div id="kb-dock" className="pb-[calc(env(safe-area-inset-bottom)+10px)] pt-1.5 px-4 bg-white">
      {uploads.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {uploads.map((name, i) => (
            <span key={i} className="flex items-center gap-1.5 bg-surface2 rounded-full px-3 py-1.5 text-[12.5px] text-ink">
              📎 {name}
              <button onClick={() => setUploads((u) => u.filter((_, j) => j !== i))} aria-label="Remove"><X size={13} className="text-ink-dim" /></button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 rounded-3xl border border-line bg-surface px-2.5 py-2 shadow-soft">
        <button aria-label="Attach" onClick={() => fileRef.current?.click()}
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-dim hover:text-ink active:scale-95 transition-all shrink-0">
          <Plus size={20} strokeWidth={1.8} />
        </button>
        <input ref={fileRef} type="file" hidden onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void pickFile(f);
        }} />
        <textarea
          ref={taRef}
          value={value}
          rows={1}
          placeholder="Ask Anything"
          onChange={(e) => { setValue(e.target.value); autoGrow(); }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          className="flex-1 bg-transparent outline-none resize-none text-[15.5px] leading-[22px] text-ink placeholder:text-ink-dim py-[9px] max-h-[132px]"
        />
        <button
          onClick={() => setFast(!fast)}
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-semibold border transition-colors ${fast ? "border-accent/40 text-accent bg-accent/5" : "border-line text-ink-dim"}`}
          aria-pressed={fast}
          title="Fast mode (visual toggle)"
        >
          Fast
        </button>
        <button aria-label="Voice input" onClick={toggleMic}
          className={`w-9 h-9 rounded-full flex items-center justify-center active:scale-95 transition-all shrink-0 ${listening ? "text-accent bg-accent/10" : "text-ink-dim hover:text-ink"}`}>
          <Mic size={19} strokeWidth={1.8} />
        </button>
        <button
          aria-label="Send"
          onClick={send}
          disabled={!value.trim()}
          className="w-9 h-9 rounded-full bg-accent text-white flex items-center justify-center disabled:bg-line disabled:text-ink-dim active:scale-95 transition-all shrink-0 shadow-soft"
        >
          <ArrowUp size={19} strokeWidth={2.4} />
        </button>
      </div>
    </div>
  );
}
