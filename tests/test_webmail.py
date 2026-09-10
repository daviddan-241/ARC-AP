"""The agent's own email: code extraction, inbox polling, and the auto-code
arena login. Pure logic runs everywhere for real; Playwright-dependent tests
run wherever Chromium can launch (the Render image ships the system libs —
the established skip-if-unlaunchable pattern from test_arena_web_provider)."""
from __future__ import annotations

import asyncio

import pytest

from arenaos.email.webmail import (
    WebmailSession,
    extract_codes,
)


# ---------------------------------------------------------------- extraction

def test_extracts_code_after_keyword():
    hits = extract_codes("Arena.ai: your verification code is 482914. It expires in 10 minutes.")
    assert hits[0][0] == "482914"


def test_extracts_code_before_keyword():
    hits = extract_codes("482014 is your WhatsApp code. Don't share it.")
    assert hits[0][0] == "482014"


def test_extracts_spaced_code():
    assert extract_codes("Your verification code is 4 8 2 9")[0][0] == "4829"
    assert extract_codes("Verify: 4 8 2 9 1 4. Expires soon")[0][0] == "482914"


def test_ignores_non_codes():
    assert extract_codes("Call me at 5551239876 or meet in room 12345.") == []
    assert extract_codes("Invoice #2026-003 attached.") == []


def test_dedup_and_order_preserved():
    text = "code 111111 ... older code 111111 ... code 222222"
    codes = [c for c, _ in extract_codes(text)]
    assert codes.count("111111") == 1
    assert codes[0] == "111111"


# ------------------------------------------------- inbox polling (fake page)

class _FakeLocator:
    async def count(self):
        return 0

    async def is_visible(self):
        return False


class _FakePage:
    """Minimal async Playwright page: serves queued inbox texts per read."""

    def is_closed(self):
        return False

    def __init__(self, texts):
        self._texts = list(texts)
        self._reads = 0
        self.url = "https://mail.google.com/mail/u/0/#inbox"

    async def close(self):
        pass

    def locator(self, _sel):
        return _FakeLocator()

    async def goto(self, *a, **k):
        pass

    async def wait_for_load_state(self, *a, **k):
        pass

    async def inner_text(self, *a, **k):
        text = self._texts[min(self._reads, len(self._texts) - 1)]
        self._reads += 1
        return text


@pytest.mark.asyncio
async def test_latest_code_waits_for_new_code_after_baseline():
    pages = [_FakePage(["old: your code is 123456"]),
             _FakePage(["old: your code is 123456",
                        "arena.ai: verification code 654321"])]
    made = iter(pages)

    async def factory():
        return next(made)

    wm = WebmailSession(factory)
    # 1st session: baseline snapshot of what's already in the inbox
    baseline_text = await wm.inbox_text()
    baseline = {c for c, _ in extract_codes(baseline_text)}
    await wm.close()
    # 2nd session: a NEW code arrives — must be returned, never the stale one
    wm2 = WebmailSession(factory)
    code = await wm2.latest_code(baseline=baseline, timeout_s=2.0, poll_s=0.01)
    await wm2.close()
    assert code == "654321"


@pytest.mark.asyncio
async def test_latest_code_times_out_without_new_mail(monkeypatch):
    page = _FakePage(["old: your code is 123456"])
    wm = WebmailSession(_page_factory(page))

    async def _fast_sleep(_):
        pass

    monkeypatch.setattr("arenaos.email.webmail.asyncio.sleep", _fast_sleep)
    with pytest.raises(TimeoutError):
        await wm.latest_code(baseline={"123456"}, timeout_s=0.05, poll_s=0.01)


def _page_factory(page):
    """Factory matching WebmailSession's new_page contract: async -> page."""
    async def factory():
        return page
    return factory


# ------------------------------------------- real-Chromium integration tests

def _can_launch_playwright() -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    async def _test() -> bool:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()
                return True
        except Exception:
            return False

    try:
        return asyncio.run(_test())
    except Exception:
        return False


PLAYWRIGHT_CAN_LAUNCH = _can_launch_playwright()

_INBOX_HTML = """<html><body>
Thread: arena.ai verification
<p>arena.ai: your verification code is 998877. It expires soon.</p>
</body></html>"""


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_webmail_reads_code_from_real_dom():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        made = False

        async def factory():
            nonlocal made
            page = await context.new_page()
            made = True
            return page

        wm = WebmailSession(
            factory, webmail_url="data:text/html;charset=utf-8," + _INBOX_HTML)
        text = await wm.inbox_text()
        codes = [c for c, _ in extract_codes(text)]
        assert "998877" in codes
        await wm.close()
        await browser.close()


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_webmail_taps_link_from_real_dom():
    from playwright.async_api import async_playwright

    landing = "data:text/html;charset=utf-8,<html><body><h1>Email Verified</h1></body></html>"
    inbox = f"""<html><body>
      <a href="{landing}">Confirm your email address</a>
      <a href="https://example.com/unrelated">Unrelated</a>
    </body></html>"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        async def factory():
            page = await context.new_page()
            await page.goto("data:text/html;charset=utf-8," + inbox)
            return page

        wm = WebmailSession(factory, webmail_url="data:text/html;charset=utf-8," + inbox)
        # tap_link calls inbox_text first (goto webmail_url), then scans links
        result = await wm.tap_link("confirm")
        await wm.close()
        await browser.close()
        assert "Email Verified" in result or landing in result
