"""Package installer: real pip/npm installs scoped to the workspace, honest apt handling.

Design reality: the container runs as a non-root `arenaos` user (security best
practice — see Dockerfile), so system apt-get installs are NOT possible at
runtime without sudo, and we don't grant sudo. Python/Node deps installed
per-workspace instead (pip --target, npm install), which needs no root and
keeps each project's dependencies isolated. If a real system package is
missing, this tool says so honestly and tells the operator (or the self-forge
lab tool) what to do instead of pretending success.
"""
from __future__ import annotations

import shutil

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import BaseTool, ToolContext, ToolResult


class InstallArgs(BaseModel):
    manager: str = Field(pattern="^(pip|npm|apt)$")
    packages: list[str] = Field(min_length=1, max_length=20)
    timeout: float = Field(default=180.0, ge=10, le=600)


class InstallPackagesTool(BaseTool):
    """Install pip/npm packages into the project workspace (no root needed); honest about apt."""

    name = "packages.install"
    description = (
        "Install packages needed for a task. manager='pip' installs into "
        "<workspace>/.deps/python (importable via PYTHONPATH). manager='npm' installs "
        "into <workspace>/node_modules. manager='apt' reports whether a system package "
        "is available and how to add it — it does not install (the container runs "
        "non-root by design)."
    )
    required_permissions = (Permission.SHELL_EXECUTE, Permission.FILESYSTEM_WRITE)
    args_model = InstallArgs

    def __init__(self, sandbox: ExecutionSandbox) -> None:
        self.sandbox = sandbox

    async def execute(self, args: InstallArgs, ctx: ToolContext) -> ToolResult:
        names = [p.strip() for p in args.packages if p.strip()]
        if not names:
            return ToolResult(ok=False, error="no valid package names given")

        if args.manager == "pip":
            target = "./.deps/python"
            cmd = f"python3 -m pip install --target {target} --no-warn-script-location " + " ".join(names)
            result = await self.sandbox.run(cmd, cwd=ctx.workspace, timeout=args.timeout, env=ctx.env)
            output = ctx.redact((result.stdout + result.stderr)[:6000])
            return ToolResult(ok=result.ok, output=output,
                              error="" if result.ok else f"pip install failed (exit {result.exit_code})",
                              meta={"target": target, "note": "add to PYTHONPATH or sys.path to import"})

        if args.manager == "npm":
            if not shutil.which("npm"):
                return ToolResult(ok=False, error="npm is not installed in this image")
            cmd = "npm install --no-audit --no-fund " + " ".join(names)
            result = await self.sandbox.run(cmd, cwd=ctx.workspace, timeout=args.timeout, env=ctx.env)
            output = ctx.redact((result.stdout + result.stderr)[:6000])
            return ToolResult(ok=result.ok, output=output,
                              error="" if result.ok else f"npm install failed (exit {result.exit_code})")

        # apt: never fake it — check what's already on the image and say so.
        found = {name: (shutil.which(name) is not None) for name in names}
        missing = [n for n, ok in found.items() if not ok]
        if not missing:
            return ToolResult(ok=True, output=f"already available: {', '.join(names)}")
        return ToolResult(
            ok=False,
            error=(f"missing system package(s): {', '.join(missing)}. This container runs "
                   f"non-root, so apt-get can't run at runtime. Add to the Dockerfile's apt-get "
                   f"install list and redeploy, or use lab.forge to build an alternative that "
                   f"only needs pip/npm."),
            meta={"found": found})
