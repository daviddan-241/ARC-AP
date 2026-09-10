"""General-purpose browser tool: the agent's own browser, usable on ANY site.

One tool, one action-oriented arg schema — mirrors how a person uses a browser:
navigate, click, type, extract text, screenshot, evaluate JS, list clickable
elements. Real Playwright calls; real errors surfaced, never faked.
"""
from __future__ import annotations

import base64
from typing import Optional

from pydantic import BaseModel, Field

from arenaos.browser.session import BrowserUnavailable, PersistentBrowser
from arenaos.browser.errors import friendly_browser_error
from arenaos.core.permissions import Permission
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

ACTIONS = ("navigate", "click", "type", "extract_text", "screenshot", "evaluate", "list_clickable")


class BrowserArgs(BaseModel):
    action: str = Field(pattern="^(" + "|".join(ACTIONS) + ")$")
    url: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    script: Optional[str] = None
    session_id: str = "default"
    timeout_ms: int = Field(default=15000, ge=1000, le=60000)


class BrowserTool(BaseTool):
    """Drive a real, persistent-profile browser: navigate/click/type/extract/screenshot on any site."""

    name = "browser"
    description = (
        "Control a real Chromium browser (persistent login/cookies across calls). "
        "actions: navigate(url), click(selector), type(selector,text), "
        "extract_text(selector optional=full page), screenshot(), evaluate(script), "
        "list_clickable() — returns candidate clickable elements with selectors."
    )
    required_permissions = (Permission.BROWSER_USE,)
    args_model = BrowserArgs

    def __init__(self, browser: PersistentBrowser) -> None:
        self.browser = browser

    async def execute(self, args: BrowserArgs, ctx: ToolContext) -> ToolResult:
        try:
            page = await self.browser.get_page(args.session_id)
        except BrowserUnavailable as exc:
            return ToolResult(ok=False, error=str(exc))

        try:
            if args.action == "navigate":
                if not args.url:
                    return ToolResult(ok=False, error="url is required for navigate")
                response = await page.goto(args.url, timeout=args.timeout_ms, wait_until="domcontentloaded")
                status = response.status if response else None
                return ToolResult(ok=True, output=f"navigated to {page.url}",
                                  meta={"status": status, "title": await page.title()})

            if args.action == "click":
                if not args.selector:
                    return ToolResult(ok=False, error="selector is required for click")
                await page.click(args.selector, timeout=args.timeout_ms)
                return ToolResult(ok=True, output=f"clicked {args.selector}")

            if args.action == "type":
                if not args.selector or args.text is None:
                    return ToolResult(ok=False, error="selector and text are required for type")
                await page.fill(args.selector, args.text, timeout=args.timeout_ms)
                return ToolResult(ok=True, output=f"typed into {args.selector}")

            if args.action == "extract_text":
                target = args.selector or "body"
                locator = page.locator(target)
                text = await locator.first.inner_text(timeout=args.timeout_ms)
                return ToolResult(ok=True, output=ctx.redact(text[:12000]))

            if args.action == "screenshot":
                png_bytes = await page.screenshot(full_page=False, timeout=args.timeout_ms)
                encoded = base64.b64encode(png_bytes).decode("ascii")
                return ToolResult(ok=True, output=f"screenshot captured ({len(png_bytes)} bytes)",
                                  meta={"png_base64": encoded})

            if args.action == "evaluate":
                if not args.script:
                    return ToolResult(ok=False, error="script is required for evaluate")
                result = await page.evaluate(args.script)
                return ToolResult(ok=True, output=ctx.redact(str(result)[:8000]))

            if args.action == "list_clickable":
                elements = await page.eval_on_selector_all(
                    "a, button, input, [role=button], [onclick]",
                    """(els) => els.slice(0, 60).map((el, i) => ({
                        i, tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 60),
                        id: el.id || null
                    }))""")
                lines = [f"[{e['i']}] <{e['tag']}> id={e['id']} text={e['text']!r}" for e in elements]
                return ToolResult(ok=True, output="\n".join(lines) or "(no clickable elements found)")

            return ToolResult(ok=False, error=f"unknown action {args.action!r}")
        except Exception as exc:  # real Playwright/timeout errors — never faked
            # One honest, human-readable line — never a raw multi-line
            # Playwright traceback / ASCII-art box shown to the agent or user.
            return ToolResult(ok=False, error=f"browser action failed: {friendly_browser_error(exc)}")
