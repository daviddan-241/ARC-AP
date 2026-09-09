"""WebSocket route for the live arena.ai login view — real cookie-session auth,
same rules as every other authenticated route (no separate weaker auth path)."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from arenaos.api.deps import SESSION_COOKIE, verify_session_token
from arenaos.browser.live_login import run_live_login
from arenaos.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["live-browser"])


@router.websocket("/ws/browser/arena-login")
async def ws_arena_login(websocket: WebSocket) -> None:
    """Stream the real arena.ai login page to the client and relay input back into it."""
    token = websocket.cookies.get(SESSION_COOKIE)
    user_id = verify_session_token(token) if token else None
    if user_id is None:
        await websocket.close(code=4401, reason="authentication required")
        return

    provider = getattr(websocket.app.state, "provider", None)
    session = getattr(provider, "session", None)
    if session is None:
        await websocket.close(code=4503, reason="arena web transport not initialized")
        return

    await run_live_login(websocket, session)
