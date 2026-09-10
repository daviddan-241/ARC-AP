"""The real tool-using agent loop: this is what makes ArenaOS DO things,
not just talk about them.

The Arena web transport scrapes a chat UI (no native function-calling), so
tool calls are a plain-text protocol the model is instructed to follow:
wrap a single call in <tool_call>{"tool": "...", "args": {...}}</tool_call>.
Anything else in the reply is treated as the final answer for that step.

Loop: build a system prompt listing every registered tool + the protocol,
send goal + running transcript to the model, parse a tool call if present,
execute it for real against the sandbox/browser via the ToolRegistry, append
the tool result to the transcript, repeat until the model gives a plain
answer or max_steps is hit. Every tool result — success or failure — is
real; nothing is fabricated to make a task look done.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from arenaos.core.logging import get_logger
from arenaos.tools.base import ToolContext, ToolRegistry

logger = get_logger(__name__)

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

CompleteFn = Callable[[list[dict[str, str]]], Awaitable[str]]


@dataclass
class AgentStep:
    kind: str  # "tool_call" | "tool_result" | "final"
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    text: str = ""


class MaxStepsExceeded(RuntimeError):
    """The loop ran to max_steps without the model producing a final answer."""


def build_system_prompt(registry: ToolRegistry, mood_prelude: str = "") -> str:
    """Persona + every real tool + the exact protocol to call one."""
    from arenaos.persona import persona_prelude
    lines = [persona_prelude(), "", mood_prelude.strip(), "",
             "Available tools (call at most one per reply):"]
    for tool in registry.list():
        schema = tool.args_model.model_json_schema().get("properties", {})
        lines.append(f"- {tool.name}: {tool.description} | args: {json.dumps(schema)}")
    lines += [
        "",
        "To call a tool, reply with EXACTLY one block and nothing else:",
        '<tool_call>{"tool": "<name>", "args": {...}}</tool_call>',
        "If a capability you need has no matching tool, use lab.forge to build it, "
        "then call the new tool.",
        "When the goal is fully done, reply in plain text with the final answer — "
        "no <tool_call> block.",
    ]
    return "\n".join(lines)


def parse_tool_call(text: str) -> Optional[dict[str, Any]]:
    """Extract a single tool call from a model reply, or None if it's a final answer."""
    match = _TOOL_CALL_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "tool" not in payload:
        return None
    return {"tool": payload["tool"], "args": payload.get("args", {}) or {}}


async def run_agent_loop(
    goal: str,
    registry: ToolRegistry,
    ctx: ToolContext,
    complete: CompleteFn,
    mood_prelude: str = "",
    max_steps: int = 8,
    on_step: Optional[Callable[[AgentStep], Awaitable[None]]] = None,
    history: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Run the plan->tool->observe loop for real. Returns {"summary", "steps", "tool_calls"}.

    `complete` is an injected async callable (message list -> reply text) so this
    loop is fully unit-testable with a scripted fake — no network/model required.
    `history` (optional prior role/content turns) is inserted before the goal so
    multi-turn conversations keep context across calls.
    """
    system_prompt = build_system_prompt(registry, mood_prelude)
    transcript: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    transcript.extend(history or [])
    transcript.append({"role": "user", "content": goal})
    steps: list[AgentStep] = []

    for step_num in range(max_steps):
        reply = await complete(transcript)
        call = parse_tool_call(reply)

        if call is None:
            step = AgentStep(kind="final", text=reply)
            steps.append(step)
            if on_step:
                await on_step(step)
            return {"summary": reply, "steps": len(steps), "tool_calls": step_num}

        transcript.append({"role": "assistant", "content": reply})
        tool_step = AgentStep(kind="tool_call", tool=call["tool"], args=call["args"])
        steps.append(tool_step)
        if on_step:
            await on_step(tool_step)

        try:
            tool = registry.get(call["tool"])
            args_obj = tool.args_model(**call["args"])
            result = await tool.execute(args_obj, ctx)
            result_payload = result.to_dict()
        except KeyError:
            result_payload = {"ok": False, "error": f"unknown tool {call['tool']!r} — "
                                                     f"use lab.forge to create it first"}
        except Exception as exc:  # bad args, tool crash — real error, fed back to the model
            result_payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        result_step = AgentStep(kind="tool_result", tool=call["tool"], result=result_payload)
        steps.append(result_step)
        if on_step:
            await on_step(result_step)

        transcript.append({"role": "tool", "content": json.dumps(result_payload)[:8000]})

    raise MaxStepsExceeded(f"goal not completed within {max_steps} steps")
