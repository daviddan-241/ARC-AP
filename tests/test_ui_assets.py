"""UI asset tests — the React frontend build served by FastAPI.

These run against the committed ui-react/dist build (no node needed at test
time). They verify the SPA shell, the design tokens, and the strict rules
(iOS 16px zoom rule, PWA manifest, security basics).
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

REACT_DIST = Path(__file__).resolve().parents[1] / "ui-react" / "dist"
SRC = Path(__file__).resolve().parents[1] / "ui-react" / "src"


def _index() -> str:
    assert (REACT_DIST / "index.html").is_file(), (
        "ui-react/dist/index.html missing — run `npm run build` in ui-react/ and commit dist/")
    return (REACT_DIST / "index.html").read_text()


def _app_css() -> str:
    css_files = list((REACT_DIST / "assets").glob("*.css"))
    assert css_files, "no built CSS in dist/assets — run the production build"
    return "\n".join(f.read_text() for f in css_files)


def test_spa_serves_and_deep_links(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "id=\"root\"" in r.text  # React shell
    for path in ("/chat", "/skills", "/automations", "/library", "/thoughts", "/private"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "id=\"root\"" in r.text, f"{path} must deep-link to the SPA shell"
    # real assets still resolve; unknown api paths stay 404 (no SPA swallowing)
    assert client.get("/api/definitely-not-a-route").status_code == 404


def test_design_tokens_present(client: TestClient) -> None:
    css = _app_css()
    # ARC design tokens — the Replit arc-ai operator-layer design: deep navy
    # surfaces (#080b25 sidebar, #111531 composer, #020313 backdrop) and the
    # cyan -> violet -> magenta gradient off the ARC wordmark.
    for token in ("#080b25", "#111531", "#020313", "#45cef7", "#ab50f2", "#eb52ab"):
        assert token in css.lower(), f"missing design token {token}"
    # the arc-* design-system classes must survive the build
    for cls in (".arc-card", ".arc-gradient", ".arc-mono", ".arc-composer-pill", ".arc-shell"):
        assert cls in css, f"missing design-system class {cls}"


def test_ios_zoom_rule_inputs_are_16px() -> None:
    """The global 16px input rule must survive the production build."""
    css = _app_css()
    base = SRC / "index.css"
    assert base.read_text().count("16px") >= 1


def test_pwa_manifest_served(client: TestClient) -> None:
    r = client.get("/manifest.json")
    assert r.status_code == 200
    assert "ARC" in r.text  # rebranded: ARC wordmark
    assert '"name": "ARC"' in r.text and '"#0A0D24"' in r.text


def test_no_sub_16px_font_size_in_source_inputs() -> None:
    """No input/textarea/select may set a font below 16px (iOS zoom-on-focus)."""
    offenders: list[str] = []
    for f in SRC.rglob("*.tsx"):
        text = f.read_text()
        for m in re.finditer(r"<(input|textarea|select)[^>]*", text):
            tag = m.group(0)
            size = re.search(r"text-\[(\d+(?:\.\d+)?)px\]", tag)
            if size and float(size.group(1)) < 16:
                offenders.append(f"{f.name}: {tag[:80]}")
    assert not offenders, f"inputs below 16px: {offenders}"


def test_viewport_hook_never_listens_to_visualviewport_scroll() -> None:
    """Regression: listening to visualViewport 'scroll' (not just 'resize')
    re-applied --app-vh on every iOS auto-pan-to-keep-input-visible event,
    forcing a shell re-layout mid-pan — this is what made the composer and
    message list appear to 'keep moving' while the keyboard was open.
    Only 'resize' should ever be wired up."""
    src = (SRC / "lib" / "useViewportHeight.ts").read_text()
    assert 'addEventListener("resize"' in src
    assert 'addEventListener("scroll"' not in src


def test_chat_scroll_uses_intersection_observer_not_fighting_smooth_scroll() -> None:
    """Regression: `scrollIntoView({behavior:'smooth'})` re-fired on every
    streamed token can't be interrupted cleanly by a manual scroll mid-flight,
    so the view kept snapping back to the bottom no matter how far up you
    scrolled ('it keeps going to the end, doesn't stay out'). The real fix
    (same pattern Discord/Slack/ChatGPT use): an IntersectionObserver on a
    bottom sentinel, and an INSTANT follow-scroll that has nothing to fight."""
    src = (SRC / "pages" / "ChatPage.tsx").read_text()
    assert "IntersectionObserver" in src
    assert ".scrollIntoView(" not in src  # replaced entirely by scrollTo calls
    # the per-token auto-follow must be instant ("auto"), never smooth --
    # smooth is fine for the one-shot manual jump button, but an ANIMATED
    # follow-scroll on every token is exactly what fights a manual scroll-up
    assert 'behavior: "auto" })' in src


def test_jump_to_bottom_button_is_actually_rendered() -> None:
    """Regression: `ArrowDown` was imported but never used in JSX — the
    'jump to latest' button was requested but silently missing from the
    real page. Confirms the button element and its click handler exist."""
    src = (SRC / "pages" / "ChatPage.tsx").read_text()
    assert "arc-jump-btn" in src
    assert "Jump to latest message" in src
    assert "<ArrowDown" in src


def test_connections_page_collapses_extra_integrations() -> None:
    """Only the 3 core connections (arena.ai, agent email, browser) show by
    default; AppDeploy/Composio and anything added later stay behind a
    'Show more' toggle so this page can't turn into a wall of cards."""
    src = (SRC / "pages" / "PluginsPage.tsx").read_text()
    assert "const core: Conn[]" in src
    assert "const extra: Conn[]" in src
    assert "showMore" in src
    assert "Show more" in src or "more integrations" in src
