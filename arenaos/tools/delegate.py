"""The `delegate` tool: real specialist sub-agent orchestration.

The main agent can hand a well-scoped subtask to a specialist (research,
coding, debugging, security, …). This runs a REAL instance of the same
agent loop — same live arena.ai provider, same tool execution sandbox —
with the specialist's prelude and a whitelist-restricted tool registry.

Safety properties, all enforced in code (not vibes):
- ONE level deep: specialists never receive the delegate tool, so no
  recursive agent trees.
- Bounded: sub-runs get a smaller max_steps than the main loop.
- Isolated: a sub-registry contains only the specialist's whitelisted
  tools, so a research specialist cannot touch git, etc.
- Honest: if the arena provider isn't initialized, the tool returns a
  real error — it never fakes a specialist answer.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from arenaos.core.logging import get_logger
from arenaos.engine.specialists import SPECIALISTS, specialist_prelude
from arenaos.tools.base import BaseTool, ToolContext, ToolRegistry, ToolResult

logger = get_logger(__name__)

# Sub-runs get fewer steps than the main loop's 8: specialists are scoped
# by design, and this bounds the worst-case cost of one delegation.
SUB_MAX_STEPS = 6


class DelegateArgs(BaseModel):
    specialist: str = Field(
        description=(
            f"Which specialist to delegate to. One of: {', '.join(sorted(SPECIALISTS))}."
        )
    )
    task: str = Field(
        description=(
            "The complete, self-contained subtask. Include every detail the "
            "specialist needs — it does NOT see this conversation."
        )
    )


class DelegateTool(BaseTool):
    """Delegate a subtask to a specialist sub-agent (real sub agent-loop)."""

    name = "delegate"
    description = (
        "Delegate one well-scoped subtask to a specialist sub-agent — a real "
        "second instance of yourself with its own toolset. Specialists: "
        + "; ".join(
            f"{n} ({' '.join(spec['tools'][:3])}…)" for n, spec in
            sorted(SPECIALISTS.items())
        )
        + ". The task must be self-contained; the specialist returns its "
          "final answer. One level deep only."
    )
    required_permissions = ()
    args_model = DelegateArgs

    def __init__(self, state_ref: dict) -> None:
        # {"get": lambda: app.state} — same lazy-reference pattern the email
        # tools use, so the tool is constructed before the state exists.
        self._state_ref = state_ref

    async def execute(self, args: DelegateArgs, ctx: ToolContext) -> ToolResult:
        if args.specialist not in SPECIALISTS:
            return ToolResult(
                ok=False,
                error=(
                    f"unknown specialist {args.specialist!r} — "
                    f"pick one of: {', '.join(sorted(SPECIALISTS))}"
                ),
            )

        # {"get": callable} — the callable is stored under the "get" key;
        # never .get() on the dict itself (that would be dict.get(key)).
        state: Any | None = self._state_ref["get"]()
        complete_fn = getattr(state, "complete_fn", None)
        main_registry: ToolRegistry | None = getattr(state, "tools", None)
        if complete_fn is None or main_registry is None:
            return ToolResult(
                ok=False,
                error=("no arena.ai provider available — the specialist sub-run "
                       "needs the live model session. Initialize the arena "
                       "session first (Settings)."),
            )

        # Build the specialist's isolated sub-registry from its whitelist.
        # Unknown names are skipped honestly (registry may evolve).
        spec = SPECIALISTS[args.specialist]
        sub_registry = ToolRegistry()
        skipped: list[str] = []
        for tool_name in spec["tools"]:
            try:
                sub_registry.register(main_registry.get(tool_name))
            except KeyError:
                skipped.append(tool_name)
        if skipped:
            logger.debug("delegate(%s): tools not in registry, skipped: %s",
                         args.specialist, ", ".join(skipped))
        if not sub_registry.list():
            return ToolResult(
                ok=False,
                error=(f"specialist {args.specialist!r} has no available tools "
                       f"in this build — nothing to run it with."),
            )

        # Imported lazily: agent_loop imports this package's base, and a
        # circular import at module load would break app startup.
        from arenaos.engine.agent_loop import run_agent_loop

        logger.info("delegate: %s sub-run starting (%d tools)",
                    args.specialist, len(sub_registry.list()))
        try:
            result = await run_agent_loop(
                goal=args.task,
                registry=sub_registry,
                ctx=ctx,
                complete=complete_fn,
                mood_prelude=specialist_prelude(args.specialist),
                max_steps=SUB_MAX_STEPS,
            )
        except Exception as exc:  # sub-loop crash: honest error, main loop continues
            logger.warning("delegate(%s) sub-run failed: %s", args.specialist, exc)
            return ToolResult(
                ok=False,
                error=f"{args.specialist} specialist failed: {type(exc).__name__}: {exc}",
            )

        summary = (f"[{args.specialist}] {result['summary']}"
                   f"\n(sub-run: {result['steps']} steps, {result['tool_calls']} tool calls)")
        logger.info("delegate: %s sub-run finished (%s steps)",
                    args.specialist, result["steps"])
        return ToolResult(ok=True, output=summary)
