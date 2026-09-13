"""SelfHost — host backend apps inside ARC's OWN Linux shell.

"…and it host backends in its shell — that's its Linux." A backend ARC
builds (with arena) can be deployed to AppDeploy for a public URL, AND/OR
hosted right here as a real tracked process in this very Linux
environment, exposed publicly through ARC's own URL at /hosted/<name>/.

Real all the way: files on disk in the sandbox workspace jail, subprocess
via ExecutionSandbox.start_background (rlimits, start_new_session, logs to
exec_logs), a port map persisted in the settings table, and an honest
liveness probe — the tool waits until the port actually accepts a
connection before reporting success.
"""
from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from arenaos.core.logging import get_logger
from arenaos.hosting import (app_dir, detect_start, get_entry, load_map,
                              next_free_port, port_alive, remove_entry,
                              set_entry)
from arenaos.tools.base import BaseTool, Permission, ToolContext, ToolResult

logger = get_logger(__name__)

PUBLIC_URL = "/hosted/{name}/"  # served by the reverse proxy router

ACTIONS = {
    "host": "Write files (optional) and launch the backend in ARC's own shell; returns the public /hosted/<name>/ URL once the port is live",
    "list": "All hosted apps with ports, commands, and live/dead status",
    "status": "One hosted app: live or dead, command, public URL",
    "logs": "Tail the real process logs",
    "stop": "Stop the hosted process (files stay; restart with action='restart')",
    "restart": "Re-launch a hosted app from its saved directory (e.g. after an app restart)",
}

HOST_TIMEOUT_S = 30.0  # generous: pip/npm installs ride the same budget
PROBE_INTERVAL_S = 0.5


class SelfHostArgs(BaseModel):
    action: str = Field(description=f"One of: {', '.join(ACTIONS)}")
    name: str | None = Field(default=None, description="The hosted app name (url-safe)")
    files: dict[str, str] | None = Field(default=None, description=(
        "host: map of relative path -> full file content to write into the "
        "app directory (optional if the files are already on disk)"))
    path: str | None = Field(default=None, description=(
        "host: optional existing directory (inside the workspaces jail) to "
        "host as-is instead of `files`"))
    command: str | None = Field(default=None, description=(
        "host/restart: explicit start command ({port} is replaced with the "
        "assigned port). Overrides auto-detection."))
    port: int | None = Field(default=None, description="host: explicit port (default: auto-probed)")


async def _wait_for_port(port: int, timeout: float = HOST_TIMEOUT_S) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if port_alive(port):
            return True
        await asyncio.sleep(PROBE_INTERVAL_S)
    return False


class SelfHostTool(BaseTool):
    """Host backends in ARC's own Linux shell — real processes, real URLs."""
    name: ClassVar[str] = "selfhost"
    description: ClassVar[str] = (
        "Host backend apps INSIDE ARC's own Linux shell as real tracked "
        "processes, exposed publicly at /hosted/<name>/ through ARC's own "
        "URL. Auto-detects the backend type (node/npm, python/uvicorn, "
        "static) or takes an explicit start command. Also pair with the "
        "appdeploy tool: AppDeploy for a standalone public URL, selfhost "
        "when the backend must run in this Linux environment.")
    required_permissions: ClassVar[list[Permission]] = [Permission.SHELL_EXECUTE, Permission.PROCESS_START]

    args_model = SelfHostArgs

    def __init__(self, sandbox) -> None:
        self.sandbox = sandbox

    async def execute(self, args: SelfHostArgs, ctx: ToolContext) -> ToolResult:
        action = args.action.strip().lower()
        if action not in ACTIONS:
            return ToolResult(ok=False, error=(
                f"unknown action '{args.action}'. Valid: {', '.join(ACTIONS)}"))
        sandbox = self.sandbox

        try:
            if action == "list":
                mapping = load_map()
                if not mapping:
                    return ToolResult(ok=True, output=(
                        "No hosted apps yet. Run action='host' with name + "
                        "files (or a path) to host a backend in ARC's shell."))
                lines = []
                for name, entry in mapping.items():
                    live = port_alive(entry.get("port", 0))
                    lines.append(
                        f"- {name}: {'LIVE' if live else 'DOWN'} at "
                        f"{PUBLIC_URL.format(name=name)} "
                        f"(port {entry.get('port')}, cmd: {entry.get('command', '')[:80]})")
                return ToolResult(ok=True, output="\n".join(lines))

            if not args.name:
                return ToolResult(ok=False, error=f"{action} needs a name")

            if action in ("host", "restart"):
                entry = get_entry(args.name)
                directory = None
                if action == "restart":
                    if entry is None:
                        return ToolResult(ok=False, error=(
                            f"no hosted app named '{args.name}' — host it first"))
                    directory = app_dir(args.name)
                else:
                    directory = (app_dir(args.name) if not args.path
                                 else None)
                if args.files:
                    if directory is None and args.path:
                        return ToolResult(ok=False, error=(
                            "pass either files= or path=, not both"))
                    if directory is None:
                        directory = app_dir(args.name)
                    for rel, content in args.files.items():
                        target = directory / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content, encoding="utf-8")
                if args.path and action == "host":
                    directory = app_dir(args.name)
                    import shutil
                    for item in _iter_source(Path(args.path)):
                        dest = directory / item.relative_to(Path(args.path))
                        if item.is_dir():
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest)

                port = args.port or (entry or {}).get("port") or next_free_port()
                command = detect_start(directory, port, args.command)

                # stop a previous handle for the same name, if any
                if entry and entry.get("handle_id"):
                    try:
                        await sandbox.stop(entry["handle_id"])
                    except KeyError:
                        pass

                handle = await sandbox.start_background(
                    command, cwd=str(directory),
                    env={"PORT": str(port), "HOST": "127.0.0.1"})

                # honest liveness: success is only reported when the port
                # actually accepts connections. Otherwise: logs + error.
                if not await _wait_for_port(port):
                    logs = sandbox.logs(handle.id, tail=3000)
                    return ToolResult(ok=False, error=(
                        f"the backend started but port {port} never came up "
                        f"within {HOST_TIMEOUT_S:.0f}s — the process may have "
                        f"crashed. Recent logs:\n{logs[-2000:]}"))

                set_entry(args.name, {
                    "port": port,
                    "handle_id": handle.id,
                    "command": command,
                    "dir": str(directory),
                })
                url = PUBLIC_URL.format(name=args.name)
                return ToolResult(ok=True, output=(
                    f"Hosted '{args.name}' in ARC's own shell (pid tracked as "
                    f"{handle.id}, port {port}). Public URL: {url}\n"
                    f"Logs: action='logs' name='{args.name}' — stop with "
                    f"action='stop'."))

            entry = get_entry(args.name)
            if entry is None:
                return ToolResult(ok=False, error=(
                    f"no hosted app named '{args.name}'. action='host' it first."))

            if action == "status":
                live = port_alive(entry.get("port", 0))
                return ToolResult(ok=True, output=(
                    f"'{args.name}' is {'LIVE' if live else 'DOWN'} at "
                    f"{PUBLIC_URL.format(name=args.name)} "
                    f"(port {entry.get('port')}, cmd: {entry.get('command', '')})"))
            if action == "logs":
                return ToolResult(ok=True, output=sandbox.logs(entry["handle_id"]))
            if action == "stop":
                try:
                    await sandbox.stop(entry["handle_id"])
                except KeyError:
                    pass  # already dead (e.g. after an app restart)
                # keep the map entry so action='restart' can relaunch it from
                # the saved directory/command — the proxy will honestly 502
                # ("process down — restart it") until it does.
                set_entry(args.name, {**entry, "handle_id": None})
                return ToolResult(ok=True, output=(
                    f"stopped '{args.name}' (files and config kept in "
                    f"{entry.get('dir')}; re-launch with action='restart')"))
            return ToolResult(ok=False, error=f"unhandled action {action}")
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:
            logger.exception("selfhost: unexpected failure")
            return ToolResult(ok=False, error=f"selfhost failure: {exc}")


def _iter_source(root: Path):
    for p in root.rglob("*"):
        if "__pycache__" in p.parts or ".git" in p.parts or "node_modules" in p.parts:
            continue
        yield p


def register_selfhost(registry, sandbox) -> None:
    registry.register(SelfHostTool(sandbox))
