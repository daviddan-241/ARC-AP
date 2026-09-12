import { useEffect } from "react";

/**
 * Real fix for the composer floating with a gap above the keyboard.
 *
 * Root cause: `100dvh` does NOT reliably shrink for the on-screen keyboard —
 * support is inconsistent across iOS Safari / Android Chrome, and the CSS
 * `interactive-widget=resizes-content` viewport hint (Chrome-only, patchy)
 * was fighting a separate JS listener in an earlier version — that's the
 * "keyboard overshoot" bug fixed before. This hook is now the ONLY mechanism:
 * it reads `window.visualViewport.height` — which every modern mobile browser
 * DOES shrink correctly when the keyboard opens — and writes it to a CSS var.
 * The app shell's height is driven by that var, so the composer (the last
 * flex child, pinned to the bottom of the shell) ends up sitting exactly on
 * top of the keyboard, with zero gap, on both iOS Safari and Android Chrome,
 * whether the app is a browser tab or an installed home-screen app.
 */
export function useViewportHeight(): void {
  useEffect(() => {
    const root = document.documentElement;
    const vv = window.visualViewport;

    const apply = (height: number) => root.style.setProperty("--app-vh", `${height}px`);

    if (!vv) {
      // very old browser with no visualViewport — 100dvh is the best we get
      apply(window.innerHeight);
      return;
    }

    const onChange = () => apply(vv.height);
    apply(vv.height);
    vv.addEventListener("resize", onChange);
    vv.addEventListener("scroll", onChange);
    return () => {
      vv.removeEventListener("resize", onChange);
      vv.removeEventListener("scroll", onChange);
    };
  }, []);
}
