"""ARC built-in browser — real page fetching + real screenshots.

Screenshots via headless Chromium CLI (works on small hosts; falls back honestly).
Text extraction via httpx. Sessions logged to /workspace/arc/browser_sessions.jsonl.
The browser runs server-side and only APPEARS in the UI when the user asks to see it.
"""
import os, time, json
from .config import get_settings
from . import terminal

S = get_settings()
SESSIONS = os.path.join(S.ARC_DATA_DIR, "arc", "browser_sessions.jsonl")
SHOTS = os.path.join(S.ARC_DATA_DIR, "output", "browser")
os.makedirs(SHOTS, exist_ok=True)


def _chromium() -> str:
    for b in ("chromium", "chromium-browser", "google-chrome", "/usr/local/bin/chromium-nosandbox"):
        path = os.popen(f"command -v {b}").read().strip() if not b.startswith("/") else (b if os.path.exists(b) else "")
        if path:
            return path
    return ""


def screenshot(url: str, width: int = 390, height: int = 844) -> dict:
    """Real headless-Chromium screenshot. Returns a media path the UI can load."""
    browser = _chromium()
    if not browser:
        return {"error": "no chromium available on this host — honest state, no fake screenshot"}
    fname = f"shot_{int(time.time()*1000)}.png"
    out = os.path.join(SHOTS, fname)
    res = terminal.run_command(
        f'{browser} --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage '
        f'--screenshot={out} --window-size={width},{height} --hide-scrollbars "{url}"',
        timeout=45)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return {"screenshot": f"/media/browser/{fname}", "url": url, "exit": res["exit_code"]}
    return {"error": f"screenshot failed (exit {res['exit_code']}) — page may block headless browsers"}


async def extract(url: str) -> dict:
    """Real text + metadata extraction."""
    import httpx
    from bs4 import BeautifulSoup
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"})
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "aside"]):
                t.decompose()
            title = soup.title.string if soup.title else ""
            text = " ".join(soup.get_text(" ", strip=True).split())[:20000]
            rec = {"url": url, "status": r.status_code, "title": title, "ts": time.time()}
            with open(SESSIONS, "a") as f:
                f.write(json.dumps(rec) + "\n")
            return {**rec, "text": text}
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}


def history(limit: int = 20) -> list:
    out = []
    try:
        lines = open(SESSIONS).readlines()[-limit:]
        for line in reversed(lines):
            try:
                d = json.loads(line)
                out.append({k: d[k] for k in ("url", "title", "ts")})
            except Exception:
                continue
    except FileNotFoundError:
        pass
    return out
