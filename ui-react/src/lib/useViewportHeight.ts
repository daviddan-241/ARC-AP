import { useEffect } from "react";

/**
 * Real fix for the composer floating with a gap above the keyboard.
 *
 * Root cause history: `100dvh` does NOT reliably shrink for the on-screen
 * keyboard — support is inconsistent across iOS Safari / Android Chrome.
 * This hook reads `window.visualViewport.height` — which every modern
 * mobile browser DOES shrink correctly when the keyboard opens — and
 * writes it to a CSS var the app shell's height is driven by.
 *
 * IMPORTANT: only listen to `resize`, never `scroll`. `visualViewport`
 * fires `scroll` whenever the visual viewport pans relative to the layout
 * viewport — which iOS Safari does on its own to keep a focused input in
 * view. Re-applying the height on every one of those pans forced a shell
 * re-layout mid-pan, which is what made the composer/message list appear
 * to "keep moving" while the keyboard was open. `resize` alone still
 * covers every real keyboard open/close and orientation change.
 */
export function useViewportHeight(): void {
  useEffect(() => {
    const root = document.documentElement;
    const vv = window.visualViewport;
    let last = -1;

    const apply = (height: number) => {
      if (height === last) return; // no-op guard: skip redundant writes
      last = height;
      root.style.setProperty("--app-vh", `${height}px`);
    };

    if (!vv) {
      // very old browser with no visualViewport — 100dvh is the best we get
      apply(window.innerHeight);
      return;
    }

    const onResize = () => apply(vv.height);
    apply(vv.height);
    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, []);
}
