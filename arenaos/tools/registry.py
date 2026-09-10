"""Builds the live ToolRegistry — every real capability the agent can invoke."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from arenaos.browser.session import PersistentBrowser
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.lab.forge import ForgeTool
from arenaos.tools.base import ToolRegistry
from arenaos.tools.browser import BrowserTool
from arenaos.tools.fs import DeleteFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from arenaos.tools.git import GitTool
from arenaos.tools.net import DownloadFileTool, HttpRequestTool, WebSearchTool
from arenaos.tools.packages import InstallPackagesTool
from arenaos.tools.shell import ShellTool


def build_registry(sandbox: ExecutionSandbox, browser: PersistentBrowser,
                   plugins_dir: Path, forge_context: dict[str, Any]) -> ToolRegistry:
    """Wire every built-in tool into one registry. Called once at app startup.

    forge_context is {"app": app, "state": app.state} — handed to lab.forge so
    newly-forged plugins can reach the live tools registry, sandbox, memory, etc.
    """
    registry = ToolRegistry()
    registry.register(ShellTool(sandbox))
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListFilesTool())
    registry.register(DeleteFileTool())
    registry.register(GitTool())
    registry.register(HttpRequestTool())
    registry.register(WebSearchTool())
    registry.register(DownloadFileTool())
    registry.register(InstallPackagesTool(sandbox))
    registry.register(BrowserTool(browser))
    from arenaos.tools.email import (
        EmailCodeTool, EmailReadTool, EmailSendTool, EmailTapLinkTool)
    email_session_ref = {"get": lambda: getattr(
        getattr(forge_context.get("state", None), "provider", None), "session", None)}
    registry.register(EmailReadTool(email_session_ref))
    registry.register(EmailCodeTool(email_session_ref))
    registry.register(EmailTapLinkTool(email_session_ref))
    registry.register(EmailSendTool(email_session_ref))
    registry.register(ForgeTool(plugins_dir, forge_context))
    return registry
