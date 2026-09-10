import { useEffect, useRef, useState } from "react";
import { Bot, X } from "lucide-react";
import { api, sha256Hex } from "../lib/api";

type Mode = "checking" | "create" | "confirm" | "locked";

export default function Pin({ onSuccess, onFallback }: { onSuccess: () => void; onFallback: () => void }) {
  const [mode, setMode] = useState<Mode>("checking");
  const [entry, setEntry] = useState("");
  const [err, setErr] = useState("");
  const pending = useRef<string | null>(null);

  // decide mode from the REAL server settings on mount
  useEffect(() => {
    let alive = true;
    api.settings()
      .then((st) => { if (alive) setMode(st.pin_hash ? "locked" : "create"); })
      .catch(() => { if (alive) setMode("create"); });
    return () => { alive = false; };
  }, []);

  const press = async (d: string) => {
    if (entry.length >= 4 || mode === "checking") return;
    const next = entry + d;
    setEntry(next);
    if (next.length < 4) return;
    const hash = await sha256Hex(next);
    if (mode === "create") {
      pending.current = hash;
      setMode("confirm");
      setEntry("");
      setErr("");
    } else if (mode === "confirm") {
      if (pending.current === hash) {
        try { await api.putSetting("pin_hash", hash); } catch { /* stored best-effort */ }
        onSuccess();
      } else {
        setMode("create");
        setEntry("");
        setErr("PINs didn't match — start over");
      }
    } else if (mode === "locked") {
      try {
        const st = await api.settings();
        if (st.pin_hash === hash) onSuccess();
        else { setEntry(""); setErr("Wrong PIN — try again"); }
      } catch { setEntry(""); setErr("Couldn't verify PIN"); }
    }
  };

  const title = { checking: "…", create: "Create your PIN", confirm: "Confirm your PIN", locked: "Enter your PIN" }[mode];
  const sub = {
    checking: "",
    create: "Pick a 4-digit PIN to unlock ArenaOS fast on this device",
    confirm: "One more time so you don't get locked out",
    locked: "Quick unlock for this device",
  }[mode];

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center">
      <div className="flex flex-col items-center px-6">
        <Bot size={36} strokeWidth={1.5} className="text-accent" />
        <h1 className="text-[22px] font-bold mt-3 text-ink">{title}</h1>
        <p className="text-[13.5px] text-ink-dim mt-1 text-center min-h-[18px]">{sub}</p>
        <div className="flex gap-4 justify-center my-8">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={`w-3.5 h-3.5 rounded-full border-2 transition-all duration-150 ${i < entry.length ? "bg-accent border-transparent scale-110" : "border-line"}`} />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-3.5 w-[264px] mx-auto">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
            <button key={d} onClick={() => press(d)} className="w-[74px] h-[74px] rounded-full bg-surface2 text-[24px] font-medium text-ink active:scale-95 active:bg-accent/10 transition-transform">{d}</button>
          ))}
          <button onClick={onFallback} className="w-[74px] h-[74px] rounded-full text-[13px] font-medium text-ink-dim hover:bg-surface active:scale-95 transition-transform">pwd</button>
          <button onClick={() => press("0")} className="w-[74px] h-[74px] rounded-full bg-surface2 text-[24px] font-medium text-ink active:scale-95 active:bg-accent/10 transition-transform">0</button>
          <button onClick={() => setEntry(entry.slice(0, -1))} aria-label="Delete" className="w-[74px] h-[74px] rounded-full flex items-center justify-center text-ink-dim hover:bg-surface active:scale-95 transition-transform"><X size={20} /></button>
        </div>
        <p className="text-[13px] text-red-500 mt-5 min-h-[18px]">{err}</p>
      </div>
    </div>
  );
}
