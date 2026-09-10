"""Live browser view for manual arena.ai login — real CDP screencast + real
input relay over a WebSocket. No demo, no simulated frames.

Danny explicitly wants to type his OWN arena.ai credentials into the real
site himself — handles 2FA/CAPTCHA the way a human would, instead of a
script auto-filling a form and tripping bot detection. This streams the
actual page (the exact persistent-profile Chromium page ArenaWebSession
already uses for automated queries) as JPEG frames over a WebSocket, and
relays clicks/typing/scroll/navigation back into that same real page.

Because it drives ArenaWebSession's own page/context, logging in here IS
the login: the moment the user reaches the chat UI, cookies are already
sitting in the shared persistent profile, and the very next automated
`send_and_wait()` call reuses them — no restart, no export/import step.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from arenaos.core.logging import get_logger
from arenaos.browser.errors import friendly_browser_error

if TYPE_CHECKING:
    from arenaos.arena.web_provider import ArenaWebSession

logger = get_logger(__name__)

FRAME_WIDTH = 480
FRAME_HEIGHT = 854


async def run_live_login(websocket: WebSocket, session: "ArenaWebSession",
                         start_url: str | None = None,
                         page: Any | None = None) -> None:
    """Drive one live browser WebSocket connection end to end against a real page.

    start_url: any site the operator asked to open (Google, Discord, banking…);
    defaults to the arena.ai chat page.
    """
    await websocket.accept()
    # Driving the arena page defers automated queries; a custom page (e.g. the
    # agent's webmail tab) doesn't conflict, so only the arena page is guarded.
    guarded = page is None
    if guarded:
        session.live_login_active = True
    cdp = None
    url_task = None
    try:
        page = page if page is not None else await session.get_page()
        await page.set_viewport_size({"width": FRAME_WIDTH, "height": FRAME_HEIGHT})
        if page.url in ("about:blank", "", None):
            await page.goto(start_url or session.config.chat_url, wait_until="domcontentloaded")

        cdp = await page.context.new_cdp_session(page)
        cdp.on("Page.screencastFrame", lambda params: asyncio.ensure_future(
            _relay_frame(websocket, cdp, params)))
        await cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 65,
            "maxWidth": FRAME_WIDTH, "maxHeight": FRAME_HEIGHT, "everyNthFrame": 1,
        })

        await websocket.send_json({"type": "url", "url": page.url})
        url_task = asyncio.ensure_future(_push_url_changes(websocket, page))

        while True:
            msg = await websocket.receive_json()
            await _apply_input(page, msg)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        # Full detail stays in the server log; the user only ever sees one
        # clean, honest sentence — never Playwright's raw ASCII-art error box.
        logger.warning("live arena login session error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "error": friendly_browser_error(exc)})
        except Exception:
            pass
    finally:
        if guarded:
            session.live_login_active = False
        if url_task:
            url_task.cancel()
        if cdp is not None:
            try:
                await cdp.send("Page.stopScreencast")
            except Exception:
                pass
        logger.info("live arena login session ended")


async def _relay_frame(websocket: WebSocket, cdp: Any, params: dict) -> None:
    """Forward one screencast frame to the browser and ack it (required by CDP)."""
    try:
        await websocket.send_json({"type": "frame", "data": params["data"]})
    except Exception:
        return
    finally:
        try:
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass


async def _push_url_changes(websocket: WebSocket, page: Any) -> None:
    """Poll the real page URL and push it whenever navigation happens."""
    last = page.url
    while True:
        await asyncio.sleep(1.0)
        if page.url != last:
            last = page.url
            try:
                await websocket.send_json({"type": "url", "url": last})
            except Exception:
                return


async def _apply_input(page: Any, msg: dict) -> None:
    """Dispatch one real input event from the client into the live page."""
    kind = msg.get("type")
    try:
        if kind == "mousemove":
            await page.mouse.move(msg["x"], msg["y"])
        elif kind == "mousedown":
            await page.mouse.move(msg["x"], msg["y"])
            await page.mouse.down()
        elif kind == "mouseup":
            await page.mouse.move(msg["x"], msg["y"])
            await page.mouse.up()
        elif kind == "click":
            await page.mouse.click(msg["x"], msg["y"])
        elif kind == "type":
            await page.keyboard.type(msg.get("text", ""))
        elif kind == "key":
            await page.keyboard.press(msg.get("key", ""))
        elif kind == "scroll":
            await page.mouse.wheel(msg.get("dx", 0), msg.get("dy", 0))
        elif kind == "goto":
            await page.goto(msg.get("url", ""), wait_until="domcontentloaded")
        elif kind == "back":
            await page.go_back()
        elif kind == "forward":
            await page.go_forward()
        elif kind == "reload":
            await page.reload()
    except Exception as exc:
        logger.debug("live-login input %r failed: %s", kind, exc)
