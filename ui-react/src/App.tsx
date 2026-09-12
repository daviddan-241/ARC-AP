import { ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BrainCircuit, ChevronDown, ChevronRight, Globe2, LibraryBig, LockKeyhole, Menu, MessageSquare,
  PlugZap, Settings2, WandSparkles, Workflow, X, Zap,
} from "lucide-react";
import { Link, Route, Switch, useLocation } from "wouter";
import { useViewportHeight } from "./lib/useViewportHeight";
import AuthGate from "./components/AuthGate";
import ArenaLoginGate from "./components/ArenaLoginGate";
import BrowserOverlay from "./components/BrowserOverlay";
import BrandMark from "./components/BrandMark";
import ChatHistory from "./components/ChatHistory";
import ChatPage from "./pages/ChatPage";
import ThoughtsPage from "./pages/ThoughtsPage";
import SkillsPage from "./pages/SkillsPage";
import AutomationsPage from "./pages/AutomationsPage";
import LibraryPage from "./pages/LibraryPage";
import PluginsPage from "./pages/PluginsPage";
import SettingsPage from "./pages/SettingsPage";
import BrowserPage from "./pages/BrowserPage";

// Only 3 primary destinations stay visible at all times — the rest live
// behind "More" so the command center reads as calm, not a control panel.
// (Danny: "most of those things should be inside their self, not more than
// three, or have a hide" — this is that hide, with a review toggle.)
const PRIMARY_NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/skills", label: "Skills", icon: WandSparkles },
  { href: "/automations", label: "Automations", icon: Workflow },
];
const MORE_NAV = [
  { href: "/thoughts", label: "Thoughts", icon: BrainCircuit },
  { href: "/library", label: "Library", icon: LibraryBig },
  { href: "/connections", label: "Connections", icon: PlugZap },
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/browser", label: "Browser", icon: Globe2 },
  { href: "/private", label: "Private chat", icon: LockKeyhole },
];
const ALL_NAV = [...PRIMARY_NAV, ...MORE_NAV];

function IconButton({ label, children, onClick }: { label: string; children: ReactNode; onClick?: () => void }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick}
    className="arc-transition inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 hover:bg-white/[.07] hover:text-white active:scale-95">{children}</button>;
}

function NavLink({ href, label, icon: I, active, onClick }: {
  href: string; label: string; icon: typeof MessageSquare; active: boolean; onClick?: () => void;
}) {
  return (
    <Link href={href} onClick={onClick}
      className={`arc-transition flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${active ? "bg-white/[.1] text-white shadow-[inset_2px_0_0_hsl(194_92%_62%)]" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>
      <I size={17} strokeWidth={1.8} /><span>{label}</span>
    </Link>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [profile, setProfile] = useState(false);
  // Collapsed by default; remembers the operator's choice once they review it.
  const [moreOpen, setMoreOpen] = useState(() => localStorage.getItem("arcNavMoreOpen") === "1");
  useEffect(() => { localStorage.setItem("arcNavMoreOpen", moreOpen ? "1" : "0"); }, [moreOpen]);

  return (
    <div className="arc-shell arc-noise flex text-slate-100">
      {/* desktop command center */}
      <aside className="arc-scroll hidden w-[238px] shrink-0 flex-col overflow-y-auto border-r border-white/[.07] bg-[#080b25]/85 px-3 py-5 md:flex">
        <Link href="/chat" className="mb-5 flex items-center gap-3 px-3">
          <BrandMark small /><span className="font-semibold tracking-[.18em] text-white">ARC<span className="text-cyan-300">.</span></span>
        </Link>

        <ChatHistory />

        <p className="arc-mono mb-2 mt-6 px-3 text-[10px] uppercase tracking-[.22em] text-slate-600">Command center</p>
        <nav className="space-y-1">
          {PRIMARY_NAV.map((item) => <NavLink key={item.href} {...item} active={location === item.href} />)}
        </nav>

        <button onClick={() => setMoreOpen((v) => !v)}
          className="arc-transition mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-500 hover:bg-white/[.05] hover:text-white">
          {moreOpen ? <ChevronDown size={17} strokeWidth={1.8} /> : <ChevronRight size={17} strokeWidth={1.8} />}
          <span>{moreOpen ? "Less" : "More"}</span>
        </button>
        <AnimatePresence initial={false}>
          {moreOpen && (
            <motion.nav initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }} className="space-y-1 overflow-hidden">
              {MORE_NAV.map((item) => <NavLink key={item.href} {...item} active={location === item.href} />)}
            </motion.nav>
          )}
        </AnimatePresence>

        <div className="mt-auto rounded-2xl border border-white/[.08] bg-gradient-to-br from-violet-500/10 to-cyan-400/[.04] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium"><Zap size={13} className="text-cyan-300" />Operator run</div>
          <p className="mb-3 text-xs leading-5 text-slate-500">Every surface here is live — no mock data anywhere.</p>
        </div>
        <div className="mt-3 flex items-center gap-3 rounded-xl p-2 text-left">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-cyan-300 to-violet-500 text-xs font-bold text-[#10142f]">DO</span>
          <span><b className="block text-xs font-medium text-white">Danny Op</b><small className="text-[11px] text-slate-500">Operator</small></span>
        </div>
      </aside>

      <div className="flex h-[var(--app-vh,100dvh)] min-h-0 min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[.07] bg-[#080b25]/70 px-4 backdrop-blur-xl md:hidden">
          <IconButton label="Open menu" onClick={() => setDrawer(true)}><Menu size={19} /></IconButton>
          <Link href="/chat" className="flex items-center gap-2"><BrandMark small /><span className="font-semibold tracking-[.16em]">ARC<span className="text-cyan-300">.</span></span></Link>
          <IconButton label="Open profile" onClick={() => setProfile(true)}>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-cyan-300 to-violet-500 text-[10px] font-bold text-[#10142f]">DO</span>
          </IconButton>
        </header>
        {/* ONE scroll owner per page, never two: main is a fixed-height slot
           (overflow-hidden). Each page manages its own internal scroll region
           (see the "h-full overflow-y-auto" wrapper each page uses). Before this,
           main scrolled AND ChatPage scrolled internally -- two nested scrollers
           meant the pinned composer could drift out of view (main would keep
           "growing" and you had to scroll main itself to reach it) instead of
           staying glued above the keyboard. */}
        <main className="arc-scroll min-w-0 flex-1 overflow-hidden">{children}</main>
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
              <div className="mb-6 flex items-center justify-between">
                <div className="flex items-center gap-3"><BrandMark small /><span className="font-semibold tracking-[.18em]">ARC<span className="text-cyan-300">.</span></span></div>
                <IconButton label="Close drawer" onClick={() => { setDrawer(false); setProfile(false); }}><X size={18} /></IconButton>
              </div>
              <div className="arc-scroll flex-1 space-y-1 overflow-y-auto">
                {drawer && (
                  <>
                    <ChatHistory onNavigate={() => setDrawer(false)} />
                    <p className="arc-mono mb-3 mt-6 text-[10px] uppercase tracking-[.22em] text-slate-600">Navigate</p>
                    {ALL_NAV.map((item) => {
                      const I = item.icon;
                      return (
                        <Link key={item.href} href={item.href} onClick={() => { setDrawer(false); setProfile(false); }}
                          className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-300 hover:bg-white/[.06]">
                          <I size={18} />{item.label}<ChevronRight size={15} className="ml-auto text-slate-600" />
                        </Link>
                      );
                    })}
                  </>
                )}
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
  useViewportHeight();

  // main no longer scrolls itself (see Shell) -- each page owns its own
  // scroll region now, so reset THAT on navigation.
  useEffect(() => {
    document.querySelector(".arc-page-scroll, .arc-chat-scroll")?.scrollTo({ top: 0 });
  }, [location]);

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
      {/* Arena.ai has NO ambient web view — it only ever appears when this
         gate needs the operator to complete login once, or when they open
         Browser themselves. See ArenaLoginGate for the one-time flow. */}
      <ArenaLoginGate />
    </AuthGate>
  );
}
