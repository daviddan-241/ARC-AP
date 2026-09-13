import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

const SESSION_FLAG = "arcArenaGateHandledThisSession";

/** Arena.ai is NOT an ambient web view in the app — it only ever appears
 * when the operator opens Browser themselves, OR right here: once, right
 * after unlocking ARC, if the live arena.ai session actually needs login.
 * We poll the real /api/status while it's open and close it automatically
 * the moment the backend reports the session is ready — no fake "logged in"
 * state, no lingering browser tab cluttering the rest of the app. */
export default function ArenaLoginGate() {
  const openBrowser = useStore((s) => s.openBrowser);
  const closeBrowser = useStore((s) => s.closeBrowser);
  const browserOpen = useStore((s) => s.browserOpen);
  const browserPage = useStore((s) => s.browserPage);
  const [gateActive, setGateActive] = useState(false);
  const pollRef = useRef<number | null>(null);

  // One check per browser session (tab lifetime) -- never nags on every
  // route change, but WILL ask again next time the app is freshly opened
  // if arena still isn't logged in.
  useEffect(() => {
    if (sessionStorage.getItem(SESSION_FLAG)) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await api.status();
        if (cancelled) return;
        const status = st.arena_session_status?.status;
        const needsLogin = st.transport === "web" && status && status !== "ready" && status !== "api_mode";
        sessionStorage.setItem(SESSION_FLAG, "1");
        if (needsLogin) {
          setGateActive(true);
          openBrowser("https://arena.ai", "arena");
        }
      } catch { /* status check failed -- don't force a browser open on a guess */ }
    })();
    return () => { cancelled = true; };
  }, [openBrowser]);

  // While the gate-triggered browser is open, poll real status; auto-close
  // the instant arena reports ready -- "then if it finishes login then it
  // shows normal" is this, driven by the real backend, not a timer guess.
  useEffect(() => {
    if (!gateActive || !browserOpen || browserPage !== "arena") return;
    pollRef.current = window.setInterval(async () => {
      try {
        const st = await api.status();
        if (st.arena_session_status?.status === "ready") {
          setGateActive(false);
          closeBrowser();
        }
      } catch { /* keep polling -- a transient network blip isn't a reason to stop */ }
    }, 4000);
    return () => { if (pollRef.current) window.clearInterval(pollRef.current); };
  }, [gateActive, browserOpen, browserPage, closeBrowser]);

  const dismiss = () => {
    setGateActive(false);
    closeBrowser();
  };

  if (!gateActive || !browserOpen || browserPage !== "arena") return null;

  return (
    <div className="fixed inset-x-0 top-0 z-[110] flex items-center justify-between gap-3 border-b border-[#E5E7EB] bg-white px-4 py-2.5 text-[12.5px] font-medium text-[#111827] shadow-lg shadow-black/[.05]"
      style={{ paddingTop: "max(0.6rem, env(safe-area-inset-top))" }}>
      <span className="flex items-center gap-2">
        <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-[#007AFF]" />
        Connect your Arena.ai account — finish the sign-in below and this closes on its own.
      </span>
      <button onClick={dismiss} aria-label="Skip for now" className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-black/[.06] text-[#374151] hover:bg-black/[.1]">
        <X size={13} />
      </button>
    </div>
  );
}
