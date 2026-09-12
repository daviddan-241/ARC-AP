"""Composio — real access to 1,500+ app integrations (Gmail, Slack, GitHub,
Notion, Calendar, …) through Composio's managed MCP gateway.

Verified live: the current gateway is https://connect.composio.dev/mcp and
speaks the standard MCP streamable-http protocol with Bearer auth. A free
account (dashboard.composio.dev) includes 100,000 tool calls/month.

Auth model (honest): the key is a real Composio API key created by the
operator in their dashboard, saved into ARC's encrypted vault via the
Settings page or the 'key' action below. It is never printed back.

Tool design: rather than wrapping 1,500 tools, this exposes the gateway's
own discovery + execution:
  * action='list'    → live tools/list of everything connected
  * action='call'    → execute any of them with real arguments
The agent is expected to call 'list' first, pick the right tool, then 'call'.
"""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from arenaos.core.logging import get_logger
from arenaos.integrations.mcp_client import MCPError, StreamableMCPClient
from arenaos.tools.base import BaseTool, Permission, ToolContext, ToolResult

logger = get_logger(__name__)

COMPOSIO_MCP = "https://connect.composio.dev/mcp"
VAULT_NAME = "composio_api_key"

ACTIONS = {
    "key": "Store your Composio API key in the vault (get it free at dashboard.composio.dev)",
    "list": "List the tools your Composio account exposes (run this first)",
    "call": "Execute one Composio tool by name with an arguments object",
}


def _client() -> StreamableMCPClient:
    try:
        from arenaos.secrets.manager import SecretsManager
        key = SecretsManager().get(VAULT_NAME)
    except Exception:
        key = None
    if not key:
        raise MCPError(
            "no Composio API key in the vault. Create a free account at "
            "https://dashboard.composio.dev, open API Keys, generate one, "
            "then run this tool with action='key' (or add it in Settings → "
            "Composio) to store it.")
    return StreamableMCPClient(COMPOSIO_MCP, api_key=key, timeout_s=120.0)


class ComposioArgs(BaseModel):
    action: str = Field(description=f"One of: {', '.join(ACTIONS)}")
    api_key: str | None = Field(default=None, description=(
        "action='key' only: the Composio API key to store (never echoed back)"))
    tool: str | None = Field(default=None, description="call: the Composio tool name from 'list'")
    arguments: dict[str, Any] | None = Field(default=None, description="call: the tool's arguments object")


class ComposioTool(BaseTool):
    """Reach 1,500+ real app integrations through the Composio gateway."""
    name: ClassVar[str] = "composio"
    description: ClassVar[str] = (
        "Call real app integrations (Gmail, Slack, GitHub, Notion, Calendar, "
        "1,500+ apps) through the live Composio MCP gateway. Needs a free "
        "Composio API key stored once (action='key'). Then action='list' to "
        "see tools, action='call' to execute one.")
    required_permissions: ClassVar[list[Permission]] = [Permission.NETWORK_REQUEST]

    args_model = ComposioArgs

    async def execute(self, args: ComposioArgs, ctx: ToolContext) -> ToolResult:
        action = args.action.strip().lower()
        if action not in ACTIONS:
            return ToolResult(ok=False, error=(
                f"unknown action '{args.action}'. Valid: {', '.join(ACTIONS)}"))
        try:
            if action == "key":
                if not args.api_key:
                    return ToolResult(ok=False, error=(
                        "pass the key with api_key=… Get one free at "
                        "https://dashboard.composio.dev → API Keys."))
                from arenaos.secrets.manager import SecretsManager
                SecretsManager().set(VAULT_NAME, "api_key", args.api_key)
                # Verify the key is real before claiming success — no fake wins.
                client = StreamableMCPClient(COMPOSIO_MCP, api_key=args.api_key)
                info = await client.initialize()
                return ToolResult(ok=True, output=(
                    f"Composio key stored and verified against the live "
                    f"gateway (server: {info.get('serverInfo', {}).get('name', 'composio')}). "
                    f"Run action='list' to see your tools."))
            client = _client()
            if action == "list":
                tools = await client.list_tools()
                if not tools:
                    return ToolResult(ok=True, output=(
                        "The gateway returned no tools — connect apps in "
                        "https://dashboard.composio.dev first."))
                lines = []
                for t in tools[:120]:
                    desc = (t.get("description") or "").strip().split("\n")[0]
                    lines.append(f"{t.get('name')}: {desc[:140]}")
                more = "" if len(tools) <= 120 else f"\n… and {len(tools) - 120} more"
                return ToolResult(ok=True, output="\n".join(lines) + more)
            # call
            if not args.tool:
                return ToolResult(ok=False, error="call needs the tool name (run action='list' first)")
            out = await client.call_tool_text(args.tool, args.arguments or {})
            return ToolResult(ok=True, output=out[:8000])
        except MCPError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:
            logger.exception("composio: unexpected failure")
            return ToolResult(ok=False, error=f"composio failure: {exc}")


def register_composio(registry) -> None:
    registry.register(ComposioTool())
