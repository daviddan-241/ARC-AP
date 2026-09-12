"""AppDeploy (appdeploy.ai) — real free hosting for apps ARC builds.

AppDeploy is a chat-native deployment platform: it takes source files and
returns a live public URL, with hosting, database, storage, auth and web
sockets built in. It exposes the standard MCP (Streamable HTTP) protocol at
https://api-v2.appdeploy.ai/mcp — we verified live that:

  * POST /mcp/api-key {"client_name": ...} provisions a REAL api key with
    no account, no email, no card (100% free, zero-setup),
  * initialize / tools/list / tools/call work with Bearer auth,
  * tools include deploy_app, get_app_status, get_apps, upload_assets,
    src_read/grep/glob, versions, rollback, secrets and QA inspection.

That MCP endpoint is normally driven from ChatGPT/Claude connectors — here
ARC drives it headless through the same protocol, so the agent can BUILD an
app with its coding tools and SHIP it to a public URL in the same turn.
The API key is stored encrypted in the vault and never printed back.
"""
from __future__ import annotations

from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field

from arenaos.core.logging import get_logger
from arenaos.integrations.mcp_client import MCPError, StreamableMCPClient
from arenaos.tools.base import BaseTool, Permission, ToolContext, ToolResult

logger = get_logger(__name__)

APPDEPLOY_MCP = "https://api-v2.appdeploy.ai/mcp"
APPDEPLOY_KEY_URL = "https://api-v2.appdeploy.ai/mcp/api-key"
VAULT_NAME = "appdeploy_api_key"

ACTIONS = {
    "key": "Provision a fresh free AppDeploy API key and store it in the vault (zero-setup, no account needed)",
    "instructions": "Fetch the real deployment rules and file constraints (call before the first deploy)",
    "template": "Fetch the official app templates for frontend-only or frontend+backend apps",
    "list": "List your deployed apps with their live URLs and status",
    "deploy": "Create or update an app and deploy it — returns when queued; follow with action=status",
    "status": "Deployment state, live URL, QA results, runtime errors and logs for one app",
    "versions": "List deployable versions of an app",
    "rollback": "Re-deploy an app at a specific prior version",
    "delete": "Permanently delete an app (only on explicit user request)",
    "call": "Raw passthrough to any AppDeploy MCP tool (upload_assets, src_read, src_grep, src_glob, set_app_secrets, get_e2e_qa_run_details, custom domains, …)",
}


def _get_key() -> str | None:
    try:
        from arenaos.secrets.manager import SecretsManager
        return SecretsManager().get(VAULT_NAME)
    except Exception:
        return None


def _client() -> StreamableMCPClient:
    key = _get_key()
    if not key:
        raise MCPError(
            "no AppDeploy API key in the vault. Fix it in one step: run this "
            "tool with action='key' — it provisions a real free key "
            "automatically (no account needed).")
    return StreamableMCPClient(APPDEPLOY_MCP, api_key=key, timeout_s=180.0)


async def provision_key() -> str:
    """Provision a real free key from AppDeploy's documented endpoint and
    store it encrypted in the vault. Returns a SAFE summary (never the key)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            APPDEPLOY_KEY_URL,
            json={"client_name": "arc-arenaos"},
            headers={"Content-Type": "application/json"})
    if res.status_code not in (200, 201):  # live-verified: 201 Created
        raise MCPError(
            f"AppDeploy key provisioning failed: HTTP {res.status_code} "
            f"{res.text[:200]}")
    data = res.json()
    api_key = data.get("api_key")
    if not api_key:
        raise MCPError(f"AppDeploy returned no api_key: {data}")
    from arenaos.secrets.manager import SecretsManager
    SecretsManager().set(VAULT_NAME, "api_key", api_key)
    logger.info("appdeploy: provisioned API key (user_id=%s)", data.get("user_id"))
    return (f"AppDeploy API key provisioned and stored encrypted in the "
            f"vault as '{VAULT_NAME}'. Account id: {data.get('user_id')}. "
            f"Manage deployed apps at https://dashboard.appdeploy.ai")


class AppDeployArgs(BaseModel):
    action: str = Field(description=(
        f"One of: {', '.join(ACTIONS)}"))
    app_id: str | None = Field(default=None, description="Target app id (for status/versions/rollback/delete/update)")
    app_name: str | None = Field(default=None, description="New app name (deploy)")
    app_type: str | None = Field(default=None,
                                    description="deploy: 'frontend-only' or 'frontend+backend'")
    template: str | None = Field(default=None,
                                   description="deploy (new apps): 'html-static' | 'react-vite' | 'nextjs-static'")
    description: str | None = Field(default=None, description="deploy: one-line app description")
    intent: str | None = Field(default=None, description="deploy: one-line summary of what changed")
    files: dict[str, str] | None = Field(default=None, description=(
        "deploy: map of relative path -> full file content, e.g. "
        "{'index.html': '<!doctype html>…'} (JSON array even for one file)"))
    version: str | None = Field(default=None, description="rollback: the version to re-deploy")
    tool: str | None = Field(default=None, description="call: the AppDeploy MCP tool name")
    arguments: dict[str, Any] | None = Field(default=None, description="call: the tool's arguments object")


class AppDeployTool(BaseTool):
    """Ship apps ARC builds to real public URLs on AppDeploy's free hosting."""
    name: ClassVar[str] = "appdeploy"
    description: ClassVar[str] = (
        "Deploy, manage and inspect real hosted apps on AppDeploy "
        "(appdeploy.ai) — free hosting with built-in database, storage, auth "
        "and public URLs. Start with action='key' once (auto-provisions a "
        "free API key), then action='instructions' and 'deploy'.")
    required_permissions: ClassVar[list[Permission]] = [Permission.NETWORK_REQUEST]

    args_model = AppDeployArgs

    async def execute(self, args: AppDeployArgs, ctx: ToolContext) -> ToolResult:
        action = args.action.strip().lower()
        if action not in ACTIONS:
            return ToolResult(ok=False, error=(
                f"unknown action '{args.action}'. Valid: {', '.join(ACTIONS)}"))
        try:
            if action == "key":
                return ToolResult(ok=True, output=await provision_key())

            client = _client()
            if action == "instructions":
                out = await client.call_tool_text("get_deploy_instructions", {})
            elif action == "template":
                out = await client.call_tool_text("get_app_template", {})
            elif action == "list":
                out = await client.call_tool_text("get_apps", {})
            elif action == "deploy":
                if not (args.app_name and args.app_type):
                    return ToolResult(ok=False, error=(
                        "deploy needs app_name and app_type "
                        "('frontend-only' or 'frontend+backend')"))
                payload: dict[str, Any] = {
                    "app_id": args.app_id,  # null => create a new app
                    "app_name": args.app_name,
                    "app_type": args.app_type,
                    "model": "arc-arenaos",
                    "intent": args.intent or "app deploy",
                    "initiator": "agent",
                }
                if args.description:
                    payload["description"] = args.description
                if not args.app_id:  # new apps need a template
                    payload["frontend_template"] = args.template or "html-static"
                if args.files:
                    payload["files"] = [
                        {"filename": name, "content": content}
                        for name, content in args.files.items()
                    ]
                out = await client.call_tool_text("deploy_app", payload)
            elif action == "status":
                if not args.app_id:
                    return ToolResult(ok=False, error="status needs app_id")
                out = await client.call_tool_text(
                    "get_app_status", {"app_id": args.app_id})
            elif action == "versions":
                if not args.app_id:
                    return ToolResult(ok=False, error="versions needs app_id")
                out = await client.call_tool_text(
                    "get_app_versions", {"app_id": args.app_id})
            elif action == "rollback":
                if not (args.app_id and args.version):
                    return ToolResult(ok=False, error="rollback needs app_id and version")
                out = await client.call_tool_text(
                    "apply_app_version",
                    {"app_id": args.app_id, "version": args.version})
            elif action == "delete":
                if not args.app_id:
                    return ToolResult(ok=False, error="delete needs app_id")
                out = await client.call_tool_text(
                    "delete_app", {"app_id": args.app_id})
            else:  # call — raw documented passthrough
                if not args.tool:
                    return ToolResult(ok=False, error="call needs tool")
                out = await client.call_tool_text(args.tool, args.arguments or {})
            return ToolResult(ok=True, output=out[:8000])
        except MCPError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:  # never swallow a real failure silently
            logger.exception("appdeploy: unexpected failure")
            return ToolResult(ok=False, error=f"appdeploy failure: {exc}")


def register_appdeploy(registry) -> None:
    registry.register(AppDeployTool())
