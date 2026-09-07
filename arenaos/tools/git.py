"""Git tool: real version control in the workspace. Push is permission-gated."""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel

from arenaos.core.permissions import Decision, Permission
from arenaos.tools.base import BaseTool, ToolContext, ToolResult


class GitArgs(BaseModel):
    op: str  # status | diff | commit | branch | checkout | clone | log | push
    message: Optional[str] = None
    branch: Optional[str] = None
    url: Optional[str] = None


class GitTool(BaseTool):
    name = "git"
    description = ("Git operations in the workspace: status, diff, log, commit, branch, "
                   "checkout, clone, push (push requires permission).")
    required_permissions = (Permission.GIT_READ,)
    args_model = GitArgs

    async def _git(self, *args: str, cwd: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        return proc.returncode or 0, out.decode("utf-8", errors="replace")[:8000]

    async def execute(self, args: GitArgs, ctx: ToolContext) -> ToolResult:
        ws = ctx.workspace
        ops = {"status": ["status"], "diff": ["diff", "HEAD"] if False else ["diff"],
               "log": ["log", "--oneline", "-20"]}
        if args.op == "clone":
            if not args.url:
                return ToolResult(ok=False, error="clone requires url")
            code, out = await self._git("clone", args.url, ".", cwd=ws)
            return ToolResult(ok=code == 0, output=out,
                              error="" if code == 0 else out,
                              meta={"exit_code": code})
        if args.op == "commit":
            if not args.message:
                return ToolResult(ok=False, error="commit requires message")
            await self._git("add", "-A", cwd=ws)
            code, out = await self._git("commit", "-m", args.message, cwd=ws)
            return ToolResult(ok=code == 0, output=out, error="" if code == 0 else out,
                              meta={"exit_code": code})
        if args.op == "branch":
            code, out = await self._git("branch", *( [args.branch] if args.branch else [] ), cwd=ws)
            return ToolResult(ok=code == 0, output=out, error="" if code == 0 else out,
                              meta={"exit_code": code})
        if args.op == "checkout":
            if not args.branch:
                return ToolResult(ok=False, error="checkout requires branch")
            code, out = await self._git("checkout", args.branch, cwd=ws)
            return ToolResult(ok=code == 0, output=out, error="" if code == 0 else out,
                              meta={"exit_code": code})
        if args.op == "push":
            if ctx.policy is None:
                return ToolResult(ok=False, error="no permission policy available — push denied")
            decision = await ctx.policy.check(Permission.GIT_PUSH)
            if decision is not Decision.ALLOW:
                return ToolResult(ok=False,
                                  error=f"git.push permission not granted (decision: {decision.value}) — "
                                        f"approve it in the UI or enable autonomous mode")
            code, out = await self._git("push", "origin", "HEAD", cwd=ws)
            return ToolResult(ok=code == 0, output=ctx.redact(out),
                              error="" if code == 0 else ctx.redact(out),
                              meta={"exit_code": code})
        if args.op in ops:
            code, out = await self._git(*ops[args.op], cwd=ws)
            return ToolResult(ok=code == 0, output=out, error="" if code == 0 else out,
                              meta={"exit_code": code})
        return ToolResult(ok=False, error=f"unknown git op {args.op!r}")
