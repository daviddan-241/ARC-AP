"""The self-upgrade "lab": when the agent hits a capability gap, it can forge a
new tool at runtime instead of failing.

How it closes the loop:
  1. The agent's tool-loop asks for a tool that doesn't exist, or an existing
     tool reports it can't do something (e.g. packages.install says a system
     binary is missing and pip/npm can't cover it).
  2. The model writes real Python for a new BaseTool subclass and calls
     lab.forge with it.
  3. This harness writes it to plugins/<name>/{manifest.json,plugin.py} —
     the SAME plugins/ directory and loader already used at boot (see
     arenaos/plugins/loader.py) — then loads it immediately (hot, no
     restart) by reusing that exact tested code path. The plugin's own
     register(context) is expected to call context["state"].tools.register(...)
     to add itself to the live registry.
  4. If it fails to import/register, the real error comes back — never a
     fabricated success — and the staged files stay on disk for inspection.
  5. On success it persists in plugins/ and the `plugins` DB table, so it
     survives restarts exactly like any other plugin.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.plugins.loader import PluginLoader
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class ForgeArgs(BaseModel):
    name: str = Field(description="lowercase-hyphen slug, e.g. 'pdf-merge'")
    description: str
    code: str = Field(description="full plugin.py source; must define register(context)")
    version: str = "1.0.0"


class ForgeTool(BaseTool):
    """Write, hot-load, and permanently register a brand-new tool. Never fakes success."""

    name = "lab.forge"
    description = (
        "Create a new capability the platform doesn't have yet. Provide Python source "
        "for a plugins/<name>/plugin.py exposing register(context) — call "
        "context['state'].tools.register(YourTool(...)) inside it to add the new tool "
        "to the live registry. On success the tool is usable immediately and survives restarts."
    )
    required_permissions = (Permission.PLUGIN_MANAGE,)
    args_model = ForgeArgs

    def __init__(self, plugins_dir: Path, forge_context: dict[str, Any]) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.forge_context = forge_context  # {"app": app, "state": app.state}

    async def execute(self, args: ForgeArgs, ctx: ToolContext) -> ToolResult:
        if not _SLUG_RE.match(args.name):
            return ToolResult(ok=False, error="name must be lowercase letters/digits/hyphens, 2-64 chars")
        if "def register" not in args.code:
            return ToolResult(ok=False, error="code must define register(context)")

        tools_registry = self.forge_context.get("state") and getattr(self.forge_context["state"], "tools", None)
        before = set(t.name for t in tools_registry.list()) if tools_registry else set()

        plugin_dir = self.plugins_dir / args.name
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"name": args.name, "version": args.version, "description": args.description,
                   "permissions": [], "forged": True}
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (plugin_dir / "plugin.py").write_text(args.code)

        loader = PluginLoader(self.plugins_dir)
        try:
            info = loader._load_one(plugin_dir, self.forge_context)
        except Exception as exc:
            # Never fake success — leave the staged files for a retry/inspection.
            return ToolResult(ok=False,
                              error=f"forge failed to load {args.name!r}: {type(exc).__name__}: {exc}",
                              meta={"staged_path": str(plugin_dir)})

        after = set(t.name for t in tools_registry.list()) if tools_registry else set()
        new_tools = sorted(after - before)
        return ToolResult(ok=True,
                          output=(f"forged and loaded plugin '{args.name}'"
                                 + (f"; new tools available: {', '.join(new_tools)}" if new_tools
                                    else " (no new tools registered — did register() call state.tools.register()?)")),
                          meta={"plugin": info, "new_tools": new_tools})
