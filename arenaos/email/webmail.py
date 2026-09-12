"""Webmail session: read the agent's own inbox and auto-extract login codes.

Real Playwright against the persistent browser profile. The operator logs
into this webmail once via the in-app browser; after that every call here is
automatic and headless.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable, Optional

import random as _random


async def human_pause(lo: float, hi: float) -> None:
    """Jittered human-like pause — fixed robotic intervals are a classic
    bot fingerprint. Every webmail action waits a slightly different,
    naturally noisy amount."""
    await asyncio.sleep(_random.uniform(lo, hi))


logger = logging.getLogger(__name__)

DEFAULT_WEBMAIL_URL = "https://mail.google.com/mail/u/0/#inbox"

# Elements that mean "this page wants a verification code".
CODE_INPUT_SELECTORS = [
    "input[autocomplete='one-time-code']",
    "input[name*='code' i]",
    "input[id*='code' i]",
    "input[placeholder*='code' i]",
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "input[inputmode='numeric']",
]

# Compose automation (Gmail-first, generic fallbacks).
COMPOSE_BUTTON_SELECTORS = [
    "div[role='button'][gh='cm']",              # Gmail Compose
    "div[aria-label*='Compose' i][role='button']",
    "button:has-text('Compose')",
]
TO_FIELD_SELECTORS = [
    "textarea[name='to']",                       # Gmail current compose
    "input[name='to']",
    "textarea[aria-label*='To' i]",
    "input[aria-label*='To' i]",
]
SUBJECT_FIELD_SELECTORS = [
    "input[name='subjectbox']",                  # Gmail
    "input[name='subject']",
    "input[aria-label*='Subject' i]",
    "input[placeholder*='Subject' i]",
]
BODY_FIELD_SELECTORS = [
    "div[aria-label*='Message Body' i]",         # Gmail
    "div[role='textbox'][contenteditable='true']",
    "textarea[name='body']",
]
SEND_BUTTON_SELECTORS = [
    "div[role='button'][aria-label*='Send' i]:not([aria-label*='more' i])",
    "button:has-text('Send')",
    "input[type='submit'][value*='Send' i]",
]

# Unread-thread markers (Gmail + generic); we try the newest unread message.
UNREAD_SELECTORS = [
    "tr.zA.zE",                                  # Gmail unread row
    "tr:has(strong)",                            # Gmail alt
    "[role='row'][aria-label*='unread' i]",
    "div[role='listitem']:has(span:has(strong))",
    "span.unread",
]

# OTP extraction — keyword before the digits, or digits before the keyword.
_CODE_BEFORE = re.compile(
    r"(?:code|otp|one[ -]?time(?: code| password| pin)?|verification|verify|"
    r"passcode|pin)\D{0,24}(?<!\d)(\d{4,8})(?!\d)",
    re.IGNORECASE,
)
_CODE_AFTER = re.compile(
    r"(?<!\d)(\d{4,8})(?!\d)\D{0,32}(?:is your|code|otp|verification|passcode)",
    re.IGNORECASE,
)
# Spaced-out codes: "your code is 4 8 2 9" / "4 8 2 9 is your code"
_CODE_SPACED = re.compile(
    r"(?:code|otp|verification|verify|passcode|pin)\D{0,24}((?:\d[ ]){3,7}\d)(?!\d)",
    re.IGNORECASE,
)
_CODE_SPACED_AFTER = re.compile(
    r"((?:\d[ ]){3,7}\d)(?!\d)\D{0,32}(?:is your|code|otp|verification|passcode)",
    re.IGNORECASE,
)


def extract_codes(text: str) -> list[tuple[str, str]]:
    """Return (code, snippet) pairs in document order.

    Gmail's inbox lists the NEWEST message first, so the first hit in inbox
    text is the freshest code. Codes already part of longer digit runs are
    excluded by the lookarounds, so phone numbers/IDs don't match.
    """
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(match: re.Match[str]) -> None:
        code = match.group(1)
        if code in seen:
            return
        seen.add(code)
        start = max(0, match.start() - 30)
        snippet = re.sub(r"\s+", " ", text[start:match.end() + 30]).strip()
        hits.append((code, snippet))

    for m in _CODE_BEFORE.finditer(text):
        add(m)
    for m in _CODE_AFTER.finditer(text):
        add(m)
    for m in list(_CODE_SPACED.finditer(text)) + list(_CODE_SPACED_AFTER.finditer(text)):
        # normalize "4 8 2 9" -> "4829" as a synthetic match object
        code = m.group(1).replace(" ", "")
        if code not in seen:
            seen.add(code)
            start = max(0, m.start() - 30)
            snippet = re.sub(r"\s+", " ", text[start:m.end() + 30]).strip()
            hits.append((code, snippet))
    return hits


class WebmailNotLoggedIn(RuntimeError):
    """The agent's webmail tab isn't logged in — the operator must open the
    in-app browser once and sign into the agent's email account."""


class WebmailSession:
    """One headless tab into the agent's webmail, in the shared browser profile."""

    def __init__(
        self,
        new_page: Callable[[], Awaitable],
        webmail_url: str = DEFAULT_WEBMAIL_URL,
    ) -> None:
        self._new_page = new_page
        self._webmail_url = webmail_url
        self._page = None

    async def _tab(self):
        if self._page is None or self._page.is_closed():
            self._page = await self._new_page()
        return self._page

    async def inbox_text(self, max_chars: int = 6000) -> str:
        """Open the inbox and return its visible text (newest messages first)."""
        page = await self._tab()
        await page.goto(self._webmail_url, wait_until="domcontentloaded", timeout=20000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            await human_pause(1.1, 2.1)  # webapps that never go idle still settle

        # Open the newest unread thread when one exists — the code lives there.
        for sel in UNREAD_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count() and await el.is_visible():
                    await el.click(timeout=3000)
                    await human_pause(0.8, 1.6)
                    break
            except Exception:
                continue

        text = (await page.inner_text("body")).strip()
        lowered = text.lower()
        if page.url.startswith("https://accounts.google.com") or (
            "sign in" in lowered and "inbox" not in lowered and "unread" not in lowered
            and "messages" not in lowered and len(text) < 1200
        ):
            raise WebmailNotLoggedIn(
                "The agent's webmail is not logged in. Open the in-app browser "
                "once, sign into the agent's email account, and this becomes automatic."
            )
        return text[:max_chars]

    async def latest_code(
        self,
        baseline: Optional[set[str]] = None,
        timeout_s: float = 100.0,
        poll_s: float = 8.0,
    ) -> str:
        """Poll the inbox for a code that arrived AFTER the baseline snapshot.

        Returns the freshest new code; raises WebmailNotLoggedIn or
        TimeoutError. baseline is the set of codes seen before the login was
        triggered, so stale codes from old mail are never reused.
        """
        baseline = baseline or set()
        deadline = asyncio.get_event_loop().time() + timeout_s
        while True:
            text = await self.inbox_text()
            fresh = [c for c, _ in extract_codes(text) if c not in baseline]
            if fresh:
                logger.info("webmail: new verification code found (%s digits)", len(fresh[0]))
                return fresh[0]
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(
                    f"No new verification code arrived in the agent's email within {timeout_s:.0f}s."
                )
            await asyncio.sleep(poll_s)

    async def tap_link(self, pattern: str) -> str:
        """Open the newest unread thread and click the first link matching
        pattern (substring of link text OR href). Returns where it landed:
        same-tab navigation or a new tab — the landing URL/title either way."""
        await self.inbox_text()  # ensures inbox is open, newest unread clicked
        page = await self._tab()
        rx = re.compile(pattern, re.IGNORECASE)
        links = page.locator("a")
        count = await links.count()
        target = None
        for i in range(min(count, 120)):
            a = links.nth(i)
            try:
                text = (await a.inner_text(timeout=2000)).strip()
            except Exception:
                text = ""
            href = await a.get_attribute("href") or ""
            if rx.search(text) or rx.search(href):
                target = a
                break
        if target is None:
            raise ValueError(f"No link matching {pattern!r} found in the inbox thread.")

        before_pages = set(p for p in page.context.pages)
        try:
            await target.click(timeout=5000)
        except Exception:
            await page.evaluate("(el) => el.click()", await target.element_handle())
        await human_pause(1.8, 3.2)

        # follow either same-tab navigation or a newly opened tab
        landing = None
        for p in page.context.pages:
            if p not in before_pages and not p.is_closed():
                landing = p
                break
        view = landing or page
        title = await view.title()
        return f"opened: {view.url} — {title}"

    async def send_email(self, to: str, subject: str, body: str) -> str:
        """Compose and send a real email from the agent's own mailbox.

        Gmail-first selectors with generic fallbacks; every failure is a real
        surfaced error, never faked success.
        """
        page = await self._tab()
        await page.goto(self._webmail_url, wait_until="domcontentloaded", timeout=20000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            await human_pause(1.1, 2.0)

        compose = None
        for sel in COMPOSE_BUTTON_SELECTORS:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                compose = loc
                break
        if compose is None:
            raise RuntimeError(
                "Compose button not found — is the agent's webmail logged in?"
            )
        await compose.click()
        await human_pause(1.1, 2.0)

        to_field = await self._first(page, TO_FIELD_SELECTORS)
        if to_field is None:
            raise RuntimeError("Compose 'To' field not found in the webmail UI.")
        await to_field.fill(to)
        await to_field.press("Tab")
        await human_pause(0.25, 0.6)

        subj = await self._first(page, SUBJECT_FIELD_SELECTORS)
        if subj:
            await subj.fill(subject)
        await human_pause(0.18, 0.45)

        body_field = await self._first(page, BODY_FIELD_SELECTORS)
        if body_field is None:
            raise RuntimeError("Compose body field not found in the webmail UI.")
        await body_field.fill(body)
        await human_pause(0.18, 0.45)

        send = await self._first(page, SEND_BUTTON_SELECTORS)
        if send is None:
            raise RuntimeError("Send button not found in the compose window.")
        await send.click()
        await human_pause(1.4, 2.6)
        return f"sent to {to}: {subject!r}"

    async def _first(self, page, selectors):
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if await loc.count() and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def close(self) -> None:
        if self._page is not None and not self._page.is_closed():
            try:
                await self._page.close()
            except Exception:
                pass
        self._page = None
