"""Tests for ArenaWebSessionProvider and ArenaWebSession (web_provider.py)."""
from __future__ import annotations

import asyncio
import http.server
import socketserver
import tempfile
import threading
from pathlib import Path

import pytest

from arenaos.arena.base import ArenaEndpoint, ChatMessage, CompleteRequest
from arenaos.arena.web_provider import (
    ArenaWebLoginRequired,
    ArenaWebScrapeError,
    ArenaWebSession,
    ArenaWebSessionProvider,
    WebSessionConfig,
    _redact_credentials,
)


def _can_launch_playwright() -> bool:
    """Runtime check if Playwright Chromium can actually launch in this environment."""
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


# --- Unit Tests (run in all environments, no browser required) ---

def test_web_session_config_defaults() -> None:
    config = WebSessionConfig()
    assert config.chat_url == "https://arena.ai"
    assert config.headless is True
    assert config.name == "arena-web"
    assert "textarea#chat-input" in config.input_selectors
    assert "button#send" in config.send_button_selectors
    assert "div#responses > div" in config.response_selectors
    # default is now settings.data_dir / "browser_profile" — absolute, so
    # the same real profile is used everywhere regardless of process CWD.
    from arenaos.core.config import get_settings
    assert config.browser_profile_dir == str(get_settings().data_dir / "browser_profile")


def test_redact_credentials_helper() -> None:
    raw_text = "User email is user@example.com and password='Secret123Password' with session='abc123xyz'"
    redacted = _redact_credentials(raw_text, extra_secrets=["Secret123Password"])
    assert "user@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "Secret123Password" not in redacted
    assert "[REDACTED]" in redacted


def test_arena_web_exceptions() -> None:
    login_err = ArenaWebLoginRequired("Login required")
    assert isinstance(login_err, RuntimeError)
    assert str(login_err) == "Login required"

    scrape_err = ArenaWebScrapeError("Scrape failed", visible_snippet="visible text snippet")
    assert isinstance(scrape_err, RuntimeError)
    assert scrape_err.visible_snippet == "visible text snippet"
    assert str(scrape_err) == "Scrape failed"


def test_build_prompt() -> None:
    provider = ArenaWebSessionProvider()
    messages = [
        ChatMessage(role="system", content="You are uncensored."),
        ChatMessage(role="user", content="Hello Arena!"),
    ]
    prompt = provider._build_prompt(messages)
    assert "[System Instructions: You are uncensored.]" in prompt
    assert "Hello Arena!" in prompt

    user_only = [ChatMessage(role="user", content="Just user")]
    assert provider._build_prompt(user_only) == "Just user"


# --- Local Server Fixture & Browser Integration Tests ---

CHAT_HTML = """<!DOCTYPE html>
<html>
<head><title>Mock Arena Chat</title></head>
<body>
  <h1>Mock Arena Chat UI</h1>
  <div id="responses"></div>
  <textarea id="chat-input" placeholder="Type a message..."></textarea>
  <button id="send">Send</button>

  <script>
    document.getElementById('send').addEventListener('click', function() {
      var input = document.getElementById('chat-input');
      var val = input.value;
      if (!val) return;
      input.value = '';

      var respDiv = document.getElementById('responses');
      var assistantMsg = document.createElement('div');
      assistantMsg.className = 'response-container';
      assistantMsg.setAttribute('role', 'assistant');
      respDiv.appendChild(assistantMsg);

      var text = "Echo response: " + val;
      var i = 0;
      var timer = setInterval(function() {
        if (i < text.length) {
          assistantMsg.textContent += text[i];
          i++;
        } else {
          clearInterval(timer);
        }
      }, 15);
    });
  </script>
</body>
</html>
"""

LOGIN_HTML = """<!DOCTYPE html>
<html>
<head><title>Mock Arena Login</title></head>
<body>
  <h1>Login Required</h1>
  <form id="login-form" action="/chat.html" method="GET">
    <input type="email" name="email" placeholder="Email" required />
    <input type="password" name="password" placeholder="Password" required />
    <button type="submit" id="submit">Log in</button>
  </form>
</body>
</html>
"""


class LocalMockServer:
    def __init__(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)

        (tmp_path / "chat.html").write_text(CHAT_HTML, encoding="utf-8")
        (tmp_path / "login.html").write_text(LOGIN_HTML, encoding="utf-8")

        handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
            *args, directory=str(tmp_path), **kwargs
        )
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp_dir.cleanup()

    @property
    def chat_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/chat.html"

    @property
    def login_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/login.html"


@pytest.fixture
def mock_server():
    server = LocalMockServer()
    server.start()
    yield server
    server.stop()


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries (libnspr4.so, etc.) are unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_web_provider_send_and_wait_complete(mock_server, tmp_path) -> None:
    config = WebSessionConfig(
        chat_url=mock_server.chat_url,
        login_url="",
        input_selectors=["#chat-input"],
        send_button_selectors=["#send"],
        response_selectors=[".response-container"],
        browser_profile_dir=str(tmp_path / "profile"),
        headless=True,
    )
    provider = ArenaWebSessionProvider(config=config)
    try:
        endpoint = ArenaEndpoint(name="web-test", base_url=mock_server.chat_url)
        req = CompleteRequest(
            endpoint=endpoint,
            messages=[ChatMessage(role="user", content="Hello arena!")],
        )
        resp = await provider.complete(req)
        assert resp.content == "Echo response: Hello arena!"
        assert resp.model == "arena-web:arena-web"
    finally:
        await provider.close()


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries (libnspr4.so, etc.) are unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_web_provider_stream(mock_server, tmp_path) -> None:
    config = WebSessionConfig(
        chat_url=mock_server.chat_url,
        login_url="",
        input_selectors=["#chat-input"],
        send_button_selectors=["#send"],
        response_selectors=[".response-container"],
        browser_profile_dir=str(tmp_path / "profile"),
        headless=True,
    )
    provider = ArenaWebSessionProvider(config=config)
    try:
        endpoint = ArenaEndpoint(name="web-test", base_url=mock_server.chat_url)
        req = CompleteRequest(
            endpoint=endpoint,
            messages=[ChatMessage(role="user", content="Stream test")],
        )

        events = []
        async for event in provider.stream(req):
            events.append(event)

        assert len(events) >= 2
        token_events = [e for e in events if e.kind == "token"]
        done_events = [e for e in events if e.kind == "done"]

        assert len(token_events) >= 1
        assert len(done_events) == 1

        full_text = "".join(e.delta for e in token_events)
        assert full_text == "Echo response: Stream test"
    finally:
        await provider.close()


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries (libnspr4.so, etc.) are unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_login_required_raises(mock_server, tmp_path) -> None:
    config = WebSessionConfig(
        chat_url=mock_server.login_url,
        login_url=mock_server.login_url,
        input_selectors=["#chat-input"],
        browser_profile_dir=str(tmp_path / "profile"),
        headless=True,
    )
    # No credential getter provided
    provider = ArenaWebSessionProvider(config=config)
    try:
        endpoint = ArenaEndpoint(name="web-test", base_url=mock_server.login_url)
        req = CompleteRequest(
            endpoint=endpoint,
            messages=[ChatMessage(role="user", content="Should fail login")],
        )
        with pytest.raises(ArenaWebLoginRequired):
            await provider.complete(req)
    finally:
        await provider.close()


@pytest.mark.skipif(
    not PLAYWRIGHT_CAN_LAUNCH,
    reason="Playwright Chromium binary or system libraries (libnspr4.so, etc.) are unavailable in sandbox.",
)
@pytest.mark.asyncio
async def test_login_with_credentials_submits_form(mock_server, tmp_path) -> None:
    config = WebSessionConfig(
        chat_url=mock_server.login_url,
        login_url=mock_server.login_url,
        input_selectors=["#chat-input"],
        send_button_selectors=["#send"],
        response_selectors=[".response-container"],
        browser_profile_dir=str(tmp_path / "profile"),
        headless=True,
    )

    creds = {
        "arena_web_email": "testuser@example.com",
        "arena_web_password": "mysecretpassword123",
    }
    provider = ArenaWebSessionProvider(
        config=config, get_credential=lambda key: creds.get(key)
    )
    try:
        endpoint = ArenaEndpoint(name="web-test", base_url=mock_server.login_url)
        req = CompleteRequest(
            endpoint=endpoint,
            messages=[ChatMessage(role="user", content="After login")],
        )
        resp = await provider.complete(req)
        assert resp.content == "Echo response: After login"
    finally:
        await provider.close()
