"""Shell tool: real command execution inside the workspace jail."""
from __future__ import annotations

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import BaseTool, ToolContext, ToolResult


class ShellArgs(BaseModel):
    command: str
    timeout: float = Field(default=60.0, ge=1, le=600)


class ShellTool(BaseTool):
    """Execute a shell command in the project workspace and return real exit code/output."""

    name = "shell"
    description = ("Run a shell command in the project workspace (bash). Returns stdout, "
                   "stderr and the real exit code.")
    required_permissions = (Permission.SHELL_EXECUTE,)
    args_model = ShellArgs

    def __init__(self, sandbox: ExecutionSandbox) -> None:
        self.sandbox = sandbox

    async def execute(self, args: ShellArgs, ctx: ToolContext) -> ToolResult:
        try:
            result = await self.sandbox.run(args.command, cwd=ctx.workspace,
                                            timeout=args.timeout, env=ctx.env)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:  # sandbox infrastructure failure — never fake success
            return ToolResult(ok=False, error=f"sandbox failure: {exc}")
        output = result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        return ToolResult(ok=result.ok, output=ctx.redact(output[:8000]),
                          error="" if result.ok else f"exit code {result.exit_code}",
                          meta={"exit_code": result.exit_code,
                                "duration_ms": result.duration_ms,
                                "stdout_path": result.stdout_path,
                                "stderr_path": result.stderr_path})
