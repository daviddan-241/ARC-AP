import { useEffect, useState } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { api } from "./lib/api";
import { useStore } from "./lib/store";
import Login from "./screens/Login";
import Pin from "./screens/Pin";
import Chat from "./screens/Chat";
import Thoughts from "./screens/Thoughts";
import Skills from "./screens/Skills";
import Automations from "./screens/Automations";
import Library from "./screens/Library";
import Private from "./screens/Private";
import Drawer from "./components/Drawer";
import Browser from "./components/Browser";
import { Menu } from "lucide-react";

/** iOS-style status bar — only rendered inside the desktop phone frame. */
function StatusBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(t);
  }, []);
  const time = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return (
    <div className="hidden md:flex items-center justify-between px-7 pt-3 pb-1 text-[13px] font-semibold text-ink select-none">
      <span>{time}</span>
      <div className="flex items-center gap-1.5">
        {/* signal · wifi · battery */}
        <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="1"/><rect x="4.5" y="5" width="3" height="6" rx="1"/><rect x="9" y="2.5" width="3" height="8.5" rx="1"/><rect x="13.5" y="0" width="3" height="11" rx="1"/></svg>
        <svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor"><path d="M8 9.5a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Zm0-3.6c1.7 0 3.3.6 4.5 1.8l1.3-1.4A8.2 8.2 0 0 0 8 4.1c-2.2 0-4.3.8-5.8 2.2l1.3 1.4A6.4 6.4 0 0 1 8 5.9Zm0-3.7c2.6 0 5 1 6.8 2.6l1.3-1.4A11 11 0 0 0 8 .4C4.8.4 1.9 1.6-.1 3.4l1.3 1.4A9.3 9.3 0 0 1 8 2.2Z" transform="translate(0.1)"/></svg>
        <svg width="25" height="12" viewBox="0 0 25 12" fill="none"><rect x="0.5" y="0.5" width="21" height="11" rx="3" stroke="currentColor" opacity="0.4"/><rect x="2" y="2" width="16" height="8" rx="1.6" fill="currentColor"/><path d="M23 4v4a2 2 0 0 0 0-4Z" fill="currentColor" opacity="0.4"/></svg>
      </div>
    </div>
  );
}

function TopBar() {
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(false);
  const mood = useStore((s) => s.mood);
  const setMood = useStore((s) => s.setMood);
  const [moods, setMoods] = useState<{ key: string }[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => { api.moods().then(setMoods).catch(() => setMoods([{ key: "uncensored" }])); }, []);

  return (
    <>
      <header className="flex items-center gap-1 px-3 pt-[calc(env(safe-area-inset-top)+10px)] pb-2 bg-white/80 backdrop-blur-md z-30">
        <button aria-label="Menu" onClick={() => setDrawer(true)} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface active:scale-95 transition-transform">
          <Menu size={21} strokeWidth={1.7} className="text-ink" />
        </button>
        <div className="relative flex-1 flex justify-center">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full hover:bg-surface text-[15px] font-semibold text-ink capitalize"
          >
            {mood.replace(/_/g, " ")}
            <svg width="10" height="6" viewBox="0 0 10 6" className={menuOpen ? "rotate-180 transition-transform" : "transition-transform"}><path d="M1 1l4 4 4-4" stroke="#6B7280" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          {menuOpen && (
            <div className="absolute top-full mt-1 w-48 bg-white rounded-2xl border border-line shadow-soft py-1.5 z-40">
              {moods.map((m) => (
                <button key={m.key} onClick={() => { setMood(m.key); setMenuOpen(false); }}
                  className={`w-full text-left px-4 py-2.5 text-[14.5px] capitalize hover:bg-surface ${m.key === mood ? "text-accent font-semibold" : "text-ink"}`}>
                  {m.key.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          )}
        </div>
        <button aria-label="New chat" onClick={() => { useStore.getState().setConversation(null); navigate("/chat"); }}
          className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-surface active:scale-95 transition-transform text-[22px] leading-none text-ink font-light">＋</button>
      </header>
      <Drawer open={drawer} onClose={() => setDrawer(false)} />
    </>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [pinDone, setPinDone] = useState(false);
  const [checking, setChecking] = useState(true);
  const setStoreAuthed = useStore((s) => s.setAuthed);

  useEffect(() => {
    (async () => {
      try {
        await api.status();
        setAuthed(true);
      } catch { setAuthed(false); }
      setChecking(false);
    })();
  }, []);

  if (checking) return <div className="min-h-screen bg-white" />;

  if (!authed) {
    return <Login onSuccess={() => { setStoreAuthed(true); setAuthed(true); }} />;
  }
  if (!pinDone) {
    return (
      <Pin
        onSuccess={() => setPinDone(true)}
        onFallback={() => { setAuthed(false); setPinDone(false); }}
      />
    );
  }

  return (
    <div style={{ height: "var(--vvh, 100dvh)" }} className="w-full flex items-center justify-center bg-[#eceef1] md:p-6">
      <div className="w-full h-full bg-white overflow-hidden relative md:w-[390px] md:h-[844px] md:rounded-[44px] md:border-[10px] md:border-[#1a1a1a] md:shadow-lift flex flex-col">
        <StatusBar />
        <TopBar />
        <div className="flex-1 overflow-hidden relative">
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/thoughts" element={<Thoughts />} />
            <Route path="/skills" element={<Skills />} />
            <Route path="/automations" element={<Automations />} />
            <Route path="/library" element={<Library />} />
            <Route path="/private" element={<Private />} />
          </Routes>
        </div>
        <Browser />
      </div>
    </div>
  );
}
