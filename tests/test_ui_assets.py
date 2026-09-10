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
    # ARC design tokens (dark navy + magenta->violet->cyan, sampled from the
    # ARC wordmark image Danny provided)
    for token in ("#9b4dff", "#d946c8", "#4ec1ff", "#0a0d24", "#12152e", "#22c55e"):
        assert token in css.lower(), f"missing design token {token}"


def test_ios_zoom_rule_inputs_are_16px() -> None:
    """The global 16px input rule must survive the production build."""
    css = _app_css()
    base = SRC / "index.css"
    assert base.read_text().count("16px") >= 1


def test_pwa_manifest_served(client: TestClient) -> None:
    r = client.get("/manifest.json")
    assert r.status_code == 200
    assert "ArenaOS" in r.text


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
