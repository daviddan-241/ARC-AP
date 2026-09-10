"""Email tools — the agent reads its own inbox, auto-fetches verification
codes, taps confirmation links, and sends real mail. All of it rides on the
webmail login the operator did ONCE via the in-app browser; cookies live in
the shared persistent Chromium profile (same profile as arena.ai).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.email.webmail import WebmailSession
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

if TYPE_CHECKING:  # pragma: no cover
    from arenaos.arena.web_provider import ArenaWebSession


class _EmailToolBase(BaseTool):
    """Shared wiring: build a WebmailSession on the arena session's profile."""

    def __init__(self, session_ref: Any) -> None:
        # session_ref resolves LAZILY: dict {"get": callable} or the session itself.
        self._session_ref = session_ref

    def _resolve_session(self) -> "ArenaWebSession":
        if isinstance(self._session_ref, dict):
            session = self._session_ref["get"]()
        else:
            session = self._session_ref
        if session is None:
            raise RuntimeError(
                "arena web session unavailable — email tools need the browser stack"
            )
        return session

    async def _webmail(self) -> WebmailSession:
        session = self._resolve_session()
        return WebmailSession(session.webmail_page, session.config.webmail_url)


class EmailReadArgs(BaseModel):
    max_chars: int = Field(default=2500, ge=200, le=8000)


class EmailReadTool(_EmailToolBase):
    """Read the agent's own inbox (newest first) — real text from the real page."""

    name = "email_read"
    description = (
        "Read the agent's own email inbox (logged-in webmail in the persistent "
        "browser profile). Returns the newest messages' visible text, newest "
        "first — subjects, snippets, codes included."
    )
    required_permissions = (Permission.BROWSER_USE,)
    args_model = EmailReadArgs

    async def execute(self, args: EmailReadArgs, ctx: ToolContext) -> ToolResult:
        wm = await self._webmail()
        try:
            text = await wm.inbox_text(max_chars=args.max_chars)
        finally:
            await wm.close()
        return ToolResult(ok=True, output=text or "(inbox empty)")


class EmailCodeArgs(BaseModel):
    timeout_s: int = Field(default=90, ge=10, le=600)


class EmailCodeTool(_EmailToolBase):
    """Auto-fetch a fresh verification/OTP code from the agent's own email."""

    name = "email_verify_code"
    description = (
        "Wait for a NEW verification code email and return the code (any site's "
        "OTP — codes that were already in the inbox are ignored). Use this when "
        "a signup/login sends a code to the agent's email."
    )
    required_permissions = (Permission.BROWSER_USE,)
    args_model = EmailCodeArgs

    async def execute(self, args: EmailCodeArgs, ctx: ToolContext) -> ToolResult:
        wm = await self._webmail()
        try:
            baseline_text = await wm.inbox_text()
            from arenaos.email.webmail import extract_codes
            baseline = {c for c, _ in extract_codes(baseline_text)}
            code = await wm.latest_code(
                baseline=baseline, timeout_s=args.timeout_s, poll_s=7.0)
        finally:
            await wm.close()
        return ToolResult(ok=True, output=code)


class EmailTapLinkArgs(BaseModel):
    pattern: str = Field(description="substring/regex of the link text or URL to click, e.g. 'confirm', 'verify your email'")


class EmailTapLinkTool(_EmailToolBase):
    """Open the newest message and click a confirmation link inside it."""

    name = "email_tap_link"
    description = (
        "Open the newest unread email and click a link inside it (confirmation "
        "links, 'verify your account', magic-login links). Returns the landing "
        "URL + page title of what the link opened."
    )
    required_permissions = (Permission.BROWSER_USE,)
    args_model = EmailTapLinkArgs

    async def execute(self, args: EmailTapLinkArgs, ctx: ToolContext) -> ToolResult:
        wm = await self._webmail()
        try:
            result = await wm.tap_link(args.pattern)
        finally:
            await wm.close()
        return ToolResult(ok=True, output=result)


class EmailSendArgs(BaseModel):
    to: str = Field(description="recipient email address")
    subject: str = ""
    body: str = Field(description="email body text")


class EmailSendTool(_EmailToolBase):
    """Compose and send a real email from the agent's own mailbox."""

    name = "email_send"
    description = (
        "Send an email from the agent's own logged-in webmail account "
        "(compose, fill to/subject/body, send — real UI automation)."
    )
    required_permissions = (Permission.BROWSER_USE,)
    args_model = EmailSendArgs

    async def execute(self, args: EmailSendArgs, ctx: ToolContext) -> ToolResult:
        wm = await self._webmail()
        try:
            result = await wm.send_email(args.to, args.subject, args.body)
        finally:
            await wm.close()
        return ToolResult(ok=True, output=result)
