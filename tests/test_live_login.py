"""Live arena.ai login: real input dispatch to a (mocked) Playwright page, and
real WebSocket auth on the route. Screencast frames themselves need a live
Chromium/CDP session — that part is exercised manually against Render, same
as the other Chromium-only tests in this suite.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from arenaos.arena.web_provider import ArenaWebLoginRequired, ArenaWebSession, WebSessionConfig
from arenaos.browser.live_login import _apply_input


def _fake_page():
    page = MagicMock()
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.down = AsyncMock()
    page.mouse.up = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.goto = AsyncMock()
    page.go_back = AsyncMock()
    page.go_forward = AsyncMock()
    page.reload = AsyncMock()
    return page


def test_apply_input_click_dispatches_real_mouse_click():
    page = _fake_page()
    asyncio.run(_apply_input(page, {"type": "click", "x": 12, "y": 34}))
    page.mouse.click.assert_awaited_once_with(12, 34)


def test_apply_input_mousedown_then_up_is_a_drag_not_a_click():
    page = _fake_page()
    asyncio.run(_apply_input(page, {"type": "mousedown", "x": 1, "y": 2}))
    asyncio.run(_apply_input(page, {"type": "mousemove", "x": 5, "y": 6}))
    asyncio.run(_apply_input(page, {"type": "mouseup", "x": 9, "y": 10}))
    page.mouse.down.assert_awaited_once()
    page.mouse.move.assert_any_await(1, 2)
    page.mouse.move.assert_any_await(5, 6)
    page.mouse.up.assert_awaited_once()
    page.mouse.click.assert_not_called()


def test_apply_input_type_sends_real_keystrokes():
    page = _fake_page()
    asyncio.run(_apply_input(page, {"type": "type", "text": "danny@example.com"}))
    page.keyboard.type.assert_awaited_once_with("danny@example.com")


def test_apply_input_key_presses_a_named_key():
    page = _fake_page()
    asyncio.run(_apply_input(page, {"type": "key", "key": "Enter"}))
    page.keyboard.press.assert_awaited_once_with("Enter")


def test_apply_input_nav_controls_hit_real_page_methods():
    page = _fake_page()
    asyncio.run(_apply_input(page, {"type": "back"}))
    asyncio.run(_apply_input(page, {"type": "forward"}))
    asyncio.run(_apply_input(page, {"type": "reload"}))
    asyncio.run(_apply_input(page, {"type": "goto", "url": "https://arena.ai/login"}))
    page.go_back.assert_awaited_once()
    page.go_forward.assert_awaited_once()
    page.reload.assert_awaited_once()
    page.goto.assert_awaited_once_with("https://arena.ai/login", wait_until="domcontentloaded")


def test_apply_input_never_raises_on_a_bad_message():
    page = _fake_page()
    page.mouse.click.side_effect = RuntimeError("page crashed")
    # must not propagate — one bad frame of input shouldn't kill the session.
    asyncio.run(_apply_input(page, {"type": "click", "x": 1, "y": 1}))


def test_send_and_wait_defers_while_live_login_is_active():
    session = ArenaWebSession(WebSessionConfig())
    session.live_login_active = True
    with pytest.raises(ArenaWebLoginRequired, match="manual arena.ai login"):
        asyncio.run(session.send_and_wait("hello"))


def test_ws_route_rejects_unauthenticated_connection():
    import os
    os.environ["ARENAOS_TEST"] = "1"
    from arenaos.api.app import app

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/browser/arena-login"):
            pass  # no session cookie -> server closes with 4401 during the handshake


def test_ws_route_rejects_when_arena_provider_unavailable():
    import os
    os.environ["ARENAOS_TEST"] = "1"
    from arenaos.api.app import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"password": os.environ.get("OPERATOR_PASSWORD", "admin")})
    assert login.status_code == 200
    # TEST_MODE never builds a real provider, so this must fail closed, not
    # silently pretend a login session started.
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/browser/arena-login"):
            pass
