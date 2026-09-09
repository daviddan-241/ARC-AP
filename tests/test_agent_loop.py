"""The real tool-using agent loop: fake model, real tools, real sandbox."""
import asyncio

from arenaos.engine.agent_loop import (MaxStepsExceeded, build_system_prompt,
                                       parse_tool_call, run_agent_loop)
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import ToolContext, ToolRegistry
from arenaos.tools.fs import ReadFileTool, WriteFileTool
from arenaos.tools.shell import ShellTool


def _registry(sandbox):
    r = ToolRegistry()
    r.register(ShellTool(sandbox))
    r.register(WriteFileTool())
    r.register(ReadFileTool())
    return r


def test_parse_tool_call_extracts_valid_json():
    text = 'sure, one sec <tool_call>{"tool": "shell", "args": {"command": "ls"}}</tool_call>'
    call = parse_tool_call(text)
    assert call == {"tool": "shell", "args": {"command": "ls"}}


def test_parse_tool_call_returns_none_for_plain_text():
    assert parse_tool_call("Here's your answer, no tool needed.") is None


def test_build_system_prompt_lists_every_tool():
    sandbox = ExecutionSandbox()
    prompt = build_system_prompt(_registry(sandbox))
    assert "shell" in prompt and "fs.write" in prompt and "<tool_call>" in prompt


def test_agent_loop_executes_real_shell_tool_then_answers():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("agent-loop-shell")
    registry = _registry(sandbox)
    ctx = ToolContext(workspace=str(ws))

    calls = {"n": 0}

    async def fake_complete(transcript):
        calls["n"] += 1
        if calls["n"] == 1:
            return '<tool_call>{"tool": "shell", "args": {"command": "echo real-output"}}</tool_call>'
        # second call: model has seen the real tool result in the transcript
        last_tool_msg = transcript[-1]["content"]
        assert "real-output" in last_tool_msg
        return "Done — the command printed real-output."

    result = asyncio.run(run_agent_loop("run echo", registry, ctx, fake_complete))
    assert result["tool_calls"] == 1
    assert "real-output" in result["summary"]


def test_agent_loop_reports_unknown_tool_without_crashing():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("agent-loop-unknown")
    registry = _registry(sandbox)
    ctx = ToolContext(workspace=str(ws))

    calls = {"n": 0}

    async def fake_complete(transcript):
        calls["n"] += 1
        if calls["n"] == 1:
            return '<tool_call>{"tool": "totally.fake", "args": {}}</tool_call>'
        assert "unknown tool" in transcript[-1]["content"]
        return "Understood, I cannot do that yet."

    result = asyncio.run(run_agent_loop("do the impossible", registry, ctx, fake_complete))
    assert "cannot do that" in result["summary"]


def test_agent_loop_writes_real_file_via_tool_call():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("agent-loop-fswrite")
    registry = _registry(sandbox)
    ctx = ToolContext(workspace=str(ws))

    async def fake_complete(transcript):
        if len(transcript) == 2:  # system + user goal only -> first turn
            return ('<tool_call>{"tool": "fs.write", '
                    '"args": {"path": "note.txt", "content": "hello from the agent"}}</tool_call>')
        return "Wrote the file."

    result = asyncio.run(run_agent_loop("save a note", registry, ctx, fake_complete))
    assert result["tool_calls"] == 1
    assert (ws / "note.txt").read_text() == "hello from the agent"


def test_agent_loop_raises_on_max_steps_without_faking_completion():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("agent-loop-maxsteps")
    registry = _registry(sandbox)
    ctx = ToolContext(workspace=str(ws))

    async def loops_forever(transcript):
        return '<tool_call>{"tool": "shell", "args": {"command": "true"}}</tool_call>'

    try:
        asyncio.run(run_agent_loop("never finish", registry, ctx, loops_forever, max_steps=2))
        assert False, "expected MaxStepsExceeded"
    except MaxStepsExceeded:
        pass


def test_agent_loop_honors_history_for_multiturn():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("agent-loop-history")
    registry = _registry(sandbox)
    ctx = ToolContext(workspace=str(ws))
    seen = {}

    async def fake_complete(transcript):
        seen["transcript"] = transcript
        return "ok"

    asyncio.run(run_agent_loop("what's next", registry, ctx, fake_complete,
                               history=[{"role": "user", "content": "my name is Danny"},
                                       {"role": "assistant", "content": "got it, Danny"}]))
    roles = [m["role"] for m in seen["transcript"]]
    assert roles == ["system", "user", "assistant", "user"]
