"""REAL probe against the live arena.ai site: discover chat selectors and test send/scrape.

Run: python scripts/arena_web_probe.py
Prints exactly what happened — no fabricated results.
"""
from __future__ import annotations

import asyncio
import sys
import time

from playwright.async_api import async_playwright

URL = "https://arena.ai"


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--js-runtime-memory-limit=192"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        print(f"[1] goto {URL}")
        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            print(f"[1] FAILED to load: {exc}")
            return 2
        await page.wait_for_timeout(4000)
        print(f"[1] landed on: {page.url}")
        print(f"[1] title: {await page.title()}")

        # Detect login walls / account gates
        body_text = (await page.inner_text("body"))[:1500]
        has_login_text = any(
            s in body_text.lower() for s in ("sign in", "log in", "sign up", "create account")
        )
        print(f"[2] login-ish text on page: {has_login_text}")

        # Find the chat input
        candidates = [
            'textarea[placeholder*="Ask anything" i]',
            "textarea",
            'div[contenteditable="true"]',
            'input[type="text"]',
        ]
        input_handle = None
        used_selector = None
        for sel in candidates:
            try:
                handle = await page.query_selector(sel)
            except Exception:
                handle = None
            if handle:
                input_handle = handle
                used_selector = sel
                break
        print(f"[3] chat input found via: {used_selector!r}")
        if input_handle is None:
            print("[3] FAILED: no chat input located")
            print("--- body snippet ---")
            print(body_text[:800])
            await browser.close()
            return 3

        # Send a real message
        message = "Reply with exactly: ArenaOS transport test OK"
        try:
            await input_handle.click()
            await input_handle.fill(message)
        except Exception:
            await input_handle.click()
            await page.keyboard.type(message, delay=5)
        print("[4] typed message, submitting with Enter")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(15000)  # let generation happen

        # Scrape candidate response containers
        response_selectors = [
            '[data-testid="assistant-message"]',
            'div[class*="assistant"]',
            'div[class*="response"]',
            'div[class*="markdown"]',
            "main div.prose",
            "main",
        ]
        found = False
        for sel in response_selectors:
            handles = await page.query_selector_all(sel)
            if handles:
                texts = []
                for h in handles[-3:]:
                    t = (await h.inner_text()).strip()
                    if t:
                        texts.append(t[:400])
                if texts:
                    print(f"[5] response candidates via {sel!r}:")
                    for t in texts:
                        print("    >>", t.replace("\n", " | ")[:400])
                    found = True
                    break
        if not found:
            print("[5] no response container matched; full body tail:")
            print((await page.inner_text("body"))[-1200:])

        await browser.close()
        print("[6] probe complete — inputs worked, responses:", found)
        return 0 if found else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
