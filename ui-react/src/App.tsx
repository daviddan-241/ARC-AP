import { ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BrainCircuit, ChevronRight, Globe2, LibraryBig, LockKeyhole, Menu, MessageSquare,
  PlugZap, Settings2, WandSparkles, Workflow, X, Zap,
} from "lucide-react";
import { Link, Route, Switch, useLocation } from "wouter";
import AuthGate from "./components/AuthGate";
import BrowserOverlay from "./components/BrowserOverlay";
import BrandMark from "./components/BrandMark";
import ChatPage from "./pages/ChatPage";
import ThoughtsPage from "./pages/ThoughtsPage";
import SkillsPage from "./pages/SkillsPage";
import AutomationsPage from "./pages/AutomationsPage";
import LibraryPage from "./pages/LibraryPage";
import PluginsPage from "./pages/PluginsPage";
import SettingsPage from "./pages/SettingsPage";
import BrowserPage from "./pages/BrowserPage";

const nav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/thoughts", label: "Thoughts", icon: BrainCircuit },
  { href: "/skills", label: "Skills", icon: WandSparkles },
  { href: "/automations", label: "Automations", icon: Workflow },
  { href: "/library", label: "Library", icon: LibraryBig },
  { href: "/connections", label: "Connections", icon: PlugZap },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

function IconButton({ label, children, onClick }: { label: string; children: ReactNode; onClick?: () => void }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick}
    className="arc-transition inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 hover:bg-white/[.07] hover:text-white active:scale-95">{children}</button>;
}

function Shell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [profile, setProfile] = useState(false);

  return (
    <div className="arc-shell arc-noise flex text-slate-100">
      {/* desktop command center */}
      <aside className="hidden w-[238px] shrink-0 flex-col border-r border-white/[.07] bg-[#080b25]/85 px-3 py-5 md:flex">
        <Link href="/chat" className="mb-7 flex items-center gap-3 px-3">
          <BrandMark small /><span className="font-semibold tracking-[.18em] text-white">ARC<span className="text-cyan-300">.</span></span>
        </Link>
        <p className="arc-mono mb-2 px-3 text-[10px] uppercase tracking-[.22em] text-slate-600">Command center</p>
        <nav className="space-y-1">
          {nav.map((item) => {
            const active = location === item.href;
            const I = item.icon;
            return (
              <Link key={item.href} href={item.href}
                className={`arc-transition flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${active ? "bg-white/[.1] text-white shadow-[inset_2px_0_0_hsl(194_92%_62%)]" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>
                <I size={17} strokeWidth={1.8} /><span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-6 border-t border-white/[.07] pt-5">
          <p className="arc-mono mb-2 px-3 text-[10px] uppercase tracking-[.22em] text-slate-600">Surfaces</p>
          <Link href="/browser" className={`arc-transition flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${location === "/browser" ? "bg-white/[.1] text-white" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>
            <Globe2 size={17} strokeWidth={1.8} /><span>Browser</span>
          </Link>
          <Link href="/private" className={`arc-transition flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${location === "/private" ? "bg-white/[.1] text-white" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>
            <LockKeyhole size={17} strokeWidth={1.8} /><span>Private chat</span>
          </Link>
        </div>
        <div className="mt-auto rounded-2xl border border-white/[.08] bg-gradient-to-br from-violet-500/10 to-cyan-400/[.04] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium"><Zap size={13} className="text-cyan-300" />Operator run</div>
          <p className="mb-3 text-xs leading-5 text-slate-500">Every surface here is live — no mock data anywhere.</p>
        </div>
        <div className="mt-3 flex items-center gap-3 rounded-xl p-2 text-left">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-cyan-300 to-violet-500 text-xs font-bold text-[#10142f]">DO</span>
          <span><b className="block text-xs font-medium text-white">Danny Op</b><small className="text-[11px] text-slate-500">Operator</small></span>
        </div>
      </aside>

      <div className="flex h-[100dvh] min-h-0 min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[.07] bg-[#080b25]/70 px-4 backdrop-blur-xl md:hidden">
          <IconButton label="Open menu" onClick={() => setDrawer(true)}><Menu size={19} /></IconButton>
          <Link href="/chat" className="flex items-center gap-2"><BrandMark small /><span className="font-semibold tracking-[.16em]">ARC<span className="text-cyan-300">.</span></span></Link>
          <IconButton label="Open profile" onClick={() => setProfile(true)}>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-cyan-300 to-violet-500 text-[10px] font-bold text-[#10142f]">DO</span>
          </IconButton>
        </header>
        <main className="arc-scroll min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* mobile drawer / profile */}
      <AnimatePresence>
        {(drawer || profile) && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-[#020313]/70 backdrop-blur-sm"
            onClick={() => { setDrawer(false); setProfile(false); }}>
            <motion.aside initial={{ x: drawer ? -300 : 380 }} animate={{ x: 0 }} exit={{ x: drawer ? -300 : 380 }}
              transition={{ type: "spring", damping: 28, stiffness: 260 }} onClick={(e) => e.stopPropagation()}
              className={`absolute ${drawer ? "left-0 border-r" : "right-0 border-l"} top-0 flex h-full w-[min(340px,88vw)] flex-col border-white/[.1] bg-[#0a0d2b] p-5 shadow-2xl`}>
              <div className="mb-8 flex items-center justify-between">
                <div className="flex items-center gap-3"><BrandMark small /><span className="font-semibold tracking-[.18em]">ARC<span className="text-cyan-300">.</span></span></div>
                <IconButton label="Close drawer" onClick={() => { setDrawer(false); setProfile(false); }}><X size={18} /></IconButton>
              </div>
              <div className="arc-scroll space-y-1 overflow-y-auto">
                <p className="arc-mono mb-3 text-[10px] uppercase tracking-[.22em] text-slate-600">Navigate</p>
                {[...nav, { href: "/browser", label: "Browser", icon: Globe2 }, { href: "/private", label: "Private chat", icon: LockKeyhole }].map((item) => {
                  const I = item.icon;
                  return (
                    <Link key={item.href} href={item.href} onClick={() => { setDrawer(false); setProfile(false); }}
                      className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-300 hover:bg-white/[.06]">
                      <I size={18} />{item.label}<ChevronRight size={15} className="ml-auto text-slate-600" />
                    </Link>
                  );
                })}
                <div className="mt-8 rounded-2xl border border-white/[.08] p-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-cyan-300 to-violet-500 text-xs font-bold text-[#10142f]">DO</span>
                    <span className="text-sm text-white">Danny Op<small className="block text-xs text-slate-500">Operator</small></span>
                  </div>
                </div>
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function App() {
  const [location] = useLocation();

  // scroll to top on navigation
  useEffect(() => { document.querySelector("main")?.scrollTo({ top: 0 }); }, [location]);

  return (
    <AuthGate>
      <Shell>
        <Switch>
          <Route path="/chat"><ChatPage /></Route>
          <Route path="/thoughts"><ThoughtsPage /></Route>
          <Route path="/skills"><SkillsPage /></Route>
          <Route path="/automations"><AutomationsPage /></Route>
          <Route path="/library"><LibraryPage /></Route>
          <Route path="/connections"><PluginsPage /></Route>
          <Route path="/settings"><SettingsPage /></Route>
          <Route path="/browser"><BrowserPage /></Route>
          <Route path="/private"><ChatPage /></Route>
          <Route path="/"><ChatPage /></Route>
          <Route><ChatPage /></Route>
        </Switch>
      </Shell>
      <BrowserOverlay />
    </AuthGate>
  );
}
