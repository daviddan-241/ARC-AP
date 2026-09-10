"""Multi-agent: the agent spawns focused sub-agents for parallel/complex work.

A sub-agent is a REAL nested run of the same plan->tool->observe loop with
its own goal and step budget. Depth is capped at 2 (a sub-agent cannot spawn
sub-agents) so work can't recurse forever.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from arenaos.engine.agent_loop import run_agent_loop
from arenaos.persona import persona_prelude
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

MAX_DEPTH = 2


class AgentSpawnArgs(BaseModel):
    goal: str = Field(description="self-contained goal for the sub-agent")
    max_steps: int = Field(default=6, ge=1, le=12)


class AgentSpawnTool(BaseTool):
    """Spawn a focused sub-agent that runs the same loop with real tools."""

    name = "agent_spawn"
    description = (
        "Spawn a sub-agent with its own goal — it plans, uses tools, and "
        "reports back a summary. Use for parallelizable pieces of a big job "
        "(e.g. 'research topic A' while you handle topic B)."
    )
    required_permissions = ()
    args_model = AgentSpawnArgs

    def __init__(self, state_ref: Any) -> None:
        # {"get": lambda: (complete_fn, registry)} — lazy so startup order is free
        self._state_ref = state_ref

    async def execute(self, args: AgentSpawnArgs, ctx: ToolContext) -> ToolResult:
        if ctx.spawn_depth + 1 >= MAX_DEPTH:
            return ToolResult(ok=False, error="sub-agent depth limit reached")
        ref = self._state_ref["get"]() if isinstance(self._state_ref, dict) else self._state_ref
        complete, registry = ref
        sub_ctx = ToolContext(
            workspace=ctx.workspace, project_id=ctx.project_id,
            task_id=ctx.task_id, env=ctx.env,
            emit=ctx.emit, redact=ctx.redact,
            spawn_depth=ctx.spawn_depth + 1,
        )
        result = await run_agent_loop(
            goal=args.goal, registry=registry, ctx=sub_ctx, complete=complete,
            mood_prelude=f"[sub-agent] Depth {ctx.spawn_depth + 1}. "
                         "Stay focused: finish the one goal, then answer.",
            max_steps=args.max_steps,
        )
        calls = ", ".join(str(c) for c in (result.get("tool_calls") or [])) or "none"
        return ToolResult(ok=True, output=(
            f"sub-agent finished — {result['summary']}\n(tools used: {calls})"))
