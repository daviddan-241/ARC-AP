"""UI regression tests: the iOS input-zoom bug and PWA/home-screen wiring.

These are static-asset checks, not browser tests — they run everywhere (no
Chromium needed) and lock in two concrete, easy-to-regress requirements:
1. No input/textarea can trigger iOS Safari's zoom-on-focus (needs >=16px).
2. Add-to-Home-Screen has a real icon and works in standalone mode.
"""
import json
import re
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1] / "arenaos" / "ui" / "static"


def test_global_font_size_rule_prevents_ios_zoom():
    css = (UI_DIR / "assets" / "css" / "app.css").read_text()
    assert re.search(r"input,\s*textarea,\s*select,\s*button\s*\{[^}]*font-size:\s*16px", css), \
        "a global >=16px rule on inputs/textareas is required to prevent iOS zoom-on-focus"


def test_no_input_or_textarea_rule_sets_a_sub_16px_font_size():
    css = (UI_DIR / "assets" / "css" / "app.css").read_text()
    # every per-selector font-size on an input/textarea-bearing rule must be >= 16px
    for match in re.finditer(r"([^{}]*\b(?:input|textarea)\b[^{}]*)\{([^}]*)\}", css):
        selector, body = match.groups()
        size_match = re.search(r"font-size:\s*([\d.]+)px", body)
        if size_match:
            assert float(size_match.group(1)) >= 16, f"{selector.strip()} sets a sub-16px font-size"


def test_manifest_exists_and_has_required_pwa_fields():
    manifest = json.loads((UI_DIR / "manifest.json").read_text())
    assert manifest["display"] == "standalone"
    assert manifest["name"] and manifest["short_name"]
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_index_html_has_apple_touch_icon_and_standalone_meta():
    html = (UI_DIR / "index.html").read_text()
    assert 'rel="apple-touch-icon"' in html
    assert 'rel="manifest"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert 'name="theme-color"' in html


def test_all_referenced_icon_files_actually_exist():
    html = (UI_DIR / "index.html").read_text()
    manifest = json.loads((UI_DIR / "manifest.json").read_text())
    referenced = set(re.findall(r'/assets/icons/([\w.-]+\.png)', html))
    referenced |= {Path(i["src"]).name for i in manifest["icons"]}
    for filename in referenced:
        assert (UI_DIR / "assets" / "icons" / filename).is_file(), f"missing icon file: {filename}"
