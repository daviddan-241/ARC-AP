import { ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AtSign, BrainCircuit, ChevronDown, ChevronRight, FolderKanban, Globe2, LibraryBig, LockKeyhole,
  LogOut, Menu, MessageSquarePlus, MoreHorizontal, Settings2, Workflow, WandSparkles, X,
} from "lucide-react";
import { Link, Route, Switch, useLocation } from "wouter";
import { useViewportHeight } from "./lib/useViewportHeight";
import { api } from "./lib/api";
import { useStore } from "./lib/store";
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
import ProjectsPage from "./pages/ProjectsPage";
import PluginsPage from "./pages/PluginsPage";
import SettingsPage from "./pages/SettingsPage";
import BrowserPage from "./pages/BrowserPage";

/* Information architecture per the light-mode spec: max 3 primary
 * destinations visible at once (Chat is the main surface; Library + Plugins
 * in the sidebar), Projects hidden completely while empty, everything else
 * behind a collapsible "More", Recents only when real chats exist. */
const PRIMARY_NAV = [
  { href: "/library", label: "Library", icon: LibraryBig },
  { href: "/connections", label: "Plugins", icon: AtSign },
];
const MORE_NAV = [
  { href: "/skills", label: "Skills", icon: WandSparkles },
  { href: "/automations", label: "Automations", icon: Workflow },
  { href: "/thoughts", label: "Thoughts", icon: BrainCircuit },
  { href: "/browser", label: "Browser", icon: Globe2 },
  { href: "/private", label: "Private chat", icon: LockKeyhole },
];

function IconButton({ label, children, onClick }: { label: string; children: ReactNode; onClick?: () => void }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick}
    className="arc-transition inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#6B7280] hover:bg-black/[.05] hover:text-[#111827] active:scale-95">{children}</button>;
}

function NavLink({ href, label, icon: I, active, onClick }: {
  href: string; label: string; icon: typeof LibraryBig; active: boolean; onClick?: () => void;
}) {
  return (
    <Link href={href} onClick={onClick}
      className={`arc-transition flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${active ? "bg-[#6366F1]/[.08] font-semibold text-[#6366F1]" : "text-[#374151] hover:bg-black/[.04] hover:text-[#111827]"}`}>
      <I size={17} strokeWidth={1.8} /><span>{label}</span>
    </Link>
  );
}

/** New Chat action — starts a genuinely fresh conversation (real store
 * reset + route change), pinned at the very top of the sidebar like the
 * reference. */
function NewChatButton({ onNavigate }: { onNavigate?: () => void }) {
  const [, navigate] = useLocation();
  const setConversation = useStore((s) => s.setConversation);
  const resetChat = useStore((s) => s.resetChat);
  return (
    <button onClick={() => { setConversation(null); resetChat(); navigate("/chat"); onNavigate?.(); }}
      className="mb-4 flex w-full items-center gap-3 rounded-2xl bg-[#6366F1] px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-[#6366F1]/25 active:scale-[.98]">
      <MessageSquarePlus size={17} />New chat
    </button>
  );
}

/** Real log-out: calls the live /api/auth/logout first, then clears client
 * auth state (AuthGate listens and re-locks the app). */
function LogoutButton({ onDone }: { onDone?: () => void }) {
  const setAuthed = useStore((s) => s.setAuthed);
  const [busy, setBusy] = useState(false);
  return (
    <button onClick={async () => {
      setBusy(true);
      try { await api.logout(); } catch { /* cookie may already be gone */ }
      setAuthed(false);
      onDone?.();
    }} disabled={busy}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-rose-600 hover:bg-rose-500/[.06] disabled:opacity-50">
      <LogOut size={17} strokeWidth={1.8} />{busy ? "Logging out…" : "Log out"}
    </button>
  );
}

/** Shared sidebar body — desktop aside and mobile drawer render the exact
 * same list so the two never drift apart. */
function SidebarBody({ location, onNavigate, onLogOut }: {
  location: string; onNavigate?: () => void; onLogOut?: () => void;
}) {
  const [moreOpen, setMoreOpen] = useState(() => localStorage.getItem("arcNavMoreOpen") === "1");
  const [projectCount, setProjectCount] = useState<number | null>(null);
  useEffect(() => {
    localStorage.setItem("arcNavMoreOpen", moreOpen ? "1" : "0");
  }, [moreOpen]);
  // Real project count — Projects stays completely hidden while it's 0.
  useEffect(() => {
    api.projects().then((p) => setProjectCount(p.length)).catch(() => setProjectCount(null));
  }, []);

  return (
    <>
      <NewChatButton onNavigate={onNavigate} />
      <nav className="space-y-1">
        <NavLink href="/chat" label="Chat" icon={MessageSquarePlus} active={location === "/chat"} onClick={onNavigate} />
        {PRIMARY_NAV.map((item) => <NavLink key={item.href} {...item} active={location === item.href} onClick={onNavigate} />)}
        {(projectCount ?? 0) > 0 && (
          <NavLink href="/projects" label="Projects" icon={FolderKanban} active={location === "/projects"} onClick={onNavigate} />
        )}
      </nav>
      <button onClick={() => setMoreOpen((v) => !v)}
        className="arc-transition mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-[#6B7280] hover:bg-black/[.04] hover:text-[#111827]">
        <MoreHorizontal size={17} strokeWidth={1.8} /><span>More</span>
        {moreOpen ? <ChevronDown size={15} className="ml-auto" /> : <ChevronRight size={15} className="ml-auto" />}
      </button>
      <AnimatePresence initial={false}>
        {moreOpen && (
          <motion.nav initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }} className="space-y-1 overflow-hidden">
            {MORE_NAV.map((item) => <NavLink key={item.href} {...item} active={location === item.href} onClick={onNavigate} />)}
            <NavLink href="/settings" label="Settings" icon={Settings2} active={location === "/settings"} onClick={onNavigate} />
          </motion.nav>
        )}
      </AnimatePresence>
      {/* Recents: REAL conversations only — the section hides entirely when
          the backend has none (no empty-state noise). */}
      <ChatHistory onNavigate={onNavigate} />
      <div className="mt-auto" />
      <div className="mt-6 border-t border-[#E5E7EB] pt-3">
        <div className="mb-2 flex items-center gap-3 px-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#6366F1] text-[11px] font-bold text-white">DO</span>
          <span><b className="block text-[13px] font-semibold text-[#111827]">Danny Op</b><small className="text-[11px] text-[#9CA3AF]">Operator</small></span>
        </div>
        <LogoutButton onDone={onLogOut} />
      </div>
    </>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [drawer, setDrawer] = useState(false);

  return (
    <div className="arc-shell flex text-[#111827]">
      {/* desktop command center */}
      <aside className="arc-scroll hidden w-[248px] shrink-0 flex-col overflow-y-auto border-r border-[#E5E7EB] bg-white px-3 py-5 md:flex">
        <Link href="/chat" className="mb-5 flex items-center gap-3 px-3">
          <BrandMark small /><span className="font-semibold tracking-[.18em] text-[#111827]">ARC<span className="text-[#6366F1]">.</span></span>
        </Link>
        <SidebarBody location={location} />
      </aside>

      <div className="flex h-[var(--app-vh,100dvh)] min-h-0 min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[#E5E7EB] bg-white/85 px-4 backdrop-blur-xl md:hidden">
          <IconButton label="Open menu" onClick={() => setDrawer(true)}><Menu size={19} /></IconButton>
          <Link href="/chat" className="flex items-center gap-2"><BrandMark small /><span className="font-semibold tracking-[.16em] text-[#111827]">ARC<span className="text-[#6366F1]">.</span></span></Link>
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#6366F1] text-[10px] font-bold text-white">DO</span>
        </header>
        {/* ONE scroll owner per page, never two: main is a fixed-height slot
           (overflow-hidden). Each page manages its own internal scroll region.
           This is what keeps the pinned composer glued above the keyboard —
           main never grows or scrolls on its own. */}
        <main className="arc-scroll min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>

      {/* mobile drawer — same body as the desktop sidebar */}
      <AnimatePresence>
        {drawer && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
            onClick={() => setDrawer(false)}>
            <motion.aside initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }}
              transition={{ type: "spring", damping: 28, stiffness: 260 }} onClick={(e) => e.stopPropagation()}
              className="absolute left-0 top-0 flex h-full w-[min(320px,88vw)] flex-col border-r border-[#E5E7EB] bg-white p-4 shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-3"><BrandMark small /><span className="font-semibold tracking-[.18em] text-[#111827]">ARC<span className="text-[#6366F1]">.</span></span></div>
                <IconButton label="Close" onClick={() => setDrawer(false)}><X size={18} /></IconButton>
              </div>
              <div className="arc-scroll flex-1 overflow-y-auto">
                <SidebarBody location={location} onNavigate={() => setDrawer(false)} onLogOut={() => setDrawer(false)} />
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

  // main no longer scrolls itself (see Shell) — each page owns its own
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
          <Route path="/projects"><ProjectsPage /></Route>
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
         Browser themselves. */}
      <ArenaLoginGate />
    </AuthGate>
  );
}
