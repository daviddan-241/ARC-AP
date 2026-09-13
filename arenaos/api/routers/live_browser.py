"""Live browser WebSocket route — streams real pages, relays real input.

Three session kinds (all authenticated by the operator cookie):
- page=arena  (default): the arena.ai page — the model-transport login
- page=webmail: the agent's own webmail tab (same arena profile)
- page=free  + url=...: ANY website on the operator's persistent profile —
  logins persist in the profile dir until cleared.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from arenaos.api.deps import SESSION_COOKIE
from arenaos.browser.live_login import run_free_browser, run_live_login
from arenaos.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/browser/arena-login")
async def ws_arena_login(websocket: WebSocket) -> None:
    """Stream a real browser page to the client and relay input back into it."""
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        await websocket.close(code=4401, reason="authentication required")
        return

    provider = getattr(websocket.app.state, "provider", None)
    # REAL BUG THIS FIXES: ArenaWebSessionProvider exposes its session as
    # `.session` (an ArenaWebSession) — `.web_session` never existed, so this
    # was ALWAYS None and the Arena/Mail overlay tabs ALWAYS showed the
    # "transport isn't running" error even when Chromium worked perfectly.
    session = getattr(provider, "session", None) if provider else None
    page_id = websocket.query_params.get("page", "arena")
    target_url = websocket.query_params.get("url")

    if page_id == "free":
        # Any site the operator asked to open — persistent profile, saved logins.
        browser = getattr(websocket.app.state, "browser", None)
        if browser is None:
            await websocket.accept()
            await websocket.send_json({"type": "error",
                "error": "Browser transport isn't running on the server "
                         "(ARENA_TRANSPORT must be 'web' and Chromium installed)."})
            await websocket.close(code=4503, reason="browser not initialized")
            return
        await run_free_browser(websocket, browser, start_url=target_url)
        return

    if session is None:
        await websocket.accept()
        await websocket.send_json({"type": "error",
            "error": "Browser transport isn't running on the server "
                     "(ARENA_TRANSPORT must be 'web' and Chromium installed). "
                     "Automated chat still works."})
        await websocket.close(code=4503, reason="arena web transport not initialized")
        return

    if page_id == "webmail":
        await run_live_login(websocket, session, page=await session.webmail_page())
    else:
        await run_live_login(websocket, session, start_url=target_url)
