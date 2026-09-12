"""Real tests for the unified specialist orchestration + knowledge vault.

No mocks of the agent loop — the delegate tool runs the REAL loop with an
injected scripted provider (same pattern as test_agent_loop.py), real fs
tools, and a real temp workspace. The knowledge tests hit the real vault
dir (conftest points DATA_DIR at a tmp dir).
"""
from __future__ import annotations

import asyncio

from pydantic import ValidationError  # noqa: F401  (kept for arg-model asserts)

from arenaos.arena.base import CORE_DIRECTIVE
from arenaos.engine.specialists import SPECIALISTS, specialist_prelude
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import ToolContext, ToolRegistry
from arenaos.tools.delegate import DelegateArgs, DelegateTool
from arenaos.tools.fs import ReadFileTool, WriteFileTool
from arenaos.tools.git import GitTool
from arenaos.tools.notes import (
    NoteBacklinksArgs, NoteListArgs, NoteReadArgs, NoteSearchArgs,
    NoteWriteArgs, NoteBacklinksTool, NoteListTool, NoteReadTool,
    NoteSearchTool, NoteWriteTool)
from arenaos.tools.shell import ShellTool


# ------------------------------------------------------------------ profiles

def test_every_specialist_prelude_layers_on_the_core_directive() -> None:
    for name in SPECIALISTS:
        prelude = specialist_prelude(name)
        assert prelude.startswith(CORE_DIRECTIVE), f"{name} lost the core directive"
        assert SPECIALISTS[name]["prelude"] in prelude


def test_unknown_specialist_raises() -> None:
    try:
        specialist_prelude("navy-seal")
        raise AssertionError("should have raised")
    except KeyError:
        pass


def test_no_specialist_can_delegate_to_another_specialist() -> None:
    """One level deep, enforced in the data: 'delegate' must never appear in
    a specialist whitelist — no recursive agent trees, ever."""
    for name, spec in SPECIALISTS.items():
        assert "delegate" not in spec["tools"], f"{name} can recurse!"
        assert "agent_spawn" not in spec["tools"], f"{name} can spawn!"


def test_security_specialist_keeps_authorized_targets_bounded() -> None:
    """The security specialist's prelude must state the authorization bound —
    this is the platform's security story: capable but bounded."""
    assert "AUTHORIZED" in specialist_prelude("security")


# ------------------------------------------------------------------ delegation

class _FakeState:
    """Looks like app.state to the DelegateTool: a complete fn + registry."""

    def __init__(self, complete_fn, tools):
        self.complete_fn = complete_fn
        self.tools = tools


def _main_registry(sandbox) -> ToolRegistry:
    r = ToolRegistry()
    r.register(ShellTool(sandbox))
    r.register(WriteFileTool())
    r.register(ReadFileTool())
    r.register(GitTool())
    r.register(DelegateTool({"get": lambda: None}))
    return r


def test_delegate_runs_a_real_sub_loop_with_the_specialist_preset() -> None:
    """End-to-end: delegate -> real run_agent_loop -> real fs.write tool ->
    scripted final answer. Proves the sub-run uses the specialist prelude
    and its isolated whitelist, and reports its own step count."""
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("delegate-e2e")
    ctx = ToolContext(workspace=str(ws), task_id="t1")

    calls: list[str] = []

    async def scripted_provider(transcript) -> str:
        system = transcript[0]["content"]
        calls.append(system)
        if len(calls) == 1:
            assert "coding specialist" in system
            assert CORE_DIRECTIVE in system
            assert "fs.write" in system and "git" in system
            return ('<tool_call>{"tool": "fs.write", "args": {"path": "proof.txt", '
                    '"content": "written by the specialist sub-run"}}</tool_call>')
        # fs.write reports a byte-count summary, not the content — check
        # the real effect (file on disk) rather than the transcript text.
        assert "wrote 33 bytes to proof.txt" in transcript[-1]["content"]
        assert (ws / "proof.txt").read_text() == "written by the specialist sub-run"
        return "subtask complete: proof.txt written"

    main = _main_registry(sandbox)
    delegate = main.get("delegate")
    delegate._state_ref = {"get": lambda: _FakeState(scripted_provider, main)}

    result = asyncio.run(delegate.execute(
        DelegateArgs(specialist="coding", task="write proof.txt"), ctx))

    assert result.ok, result.error
    assert "[coding] subtask complete" in result.output
    assert "sub-run: 3 steps, 1 tool calls" in result.output
    assert (ws / "proof.txt").exists()
    assert (ws / "proof.txt").read_text() == "written by the specialist sub-run"
    # the sub-run must NEVER see the delegate tool in its own system prompt
    assert "delegate to a specialist" not in calls[0]


def test_delegate_rejects_unknown_specialist_honestly() -> None:
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("delegate-bad")
    delegate = DelegateTool({"get": lambda: _FakeState(None, None)})
    result = asyncio.run(delegate.execute(
        DelegateArgs(specialist="wizard", task="x"),
        ToolContext(workspace=str(ws))))
    assert not result.ok
    assert "unknown specialist" in result.error


def test_delegate_without_a_provider_returns_a_real_error() -> None:
    """No arena session = honest 'can't run' — NEVER a faked specialist answer."""
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("delegate-noprovider")
    delegate = DelegateTool({"get": lambda: _FakeState(None, _main_registry(sandbox))})
    result = asyncio.run(delegate.execute(
        DelegateArgs(specialist="research", task="find sources"),
        ToolContext(workspace=str(ws))))
    assert not result.ok
    assert "no arena.ai provider" in result.error


def test_delegate_skips_whitelisted_tools_missing_from_the_registry() -> None:
    """A whitelist references tools that don't exist in this build (git isn't
    registered here) — the sub-registry skips them and the run still works."""
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("delegate-skip")
    r = ToolRegistry()
    r.register(WriteFileTool())  # fs.write only; whitelist's git is missing

    async def provider(transcript) -> str:
        return "ok"

    delegate = DelegateTool({"get": lambda: _FakeState(provider, r)})
    result = asyncio.run(delegate.execute(
        DelegateArgs(specialist="coding", task="small change"),
        ToolContext(workspace=str(ws))))
    assert result.ok
    assert "[coding]" in result.output


# ------------------------------------------------------------------ knowledge

def _run(tool, args):
    return asyncio.run(tool.execute(args, ToolContext(workspace="/nonexistent", task_id="notes-test")))


def test_note_write_with_folder_and_tags_then_list_and_read() -> None:
    res = _run(NoteWriteTool(), NoteWriteArgs(
        title="Market Map", content="See [[Competitors]] too.",
        folder="research/markets", tags=["research", "2026"]))
    assert res.ok
    assert "research/markets/Market-Map.md" in res.output
    assert "(tags: research, 2026)" in res.output

    listing = _run(NoteListTool(), NoteListArgs())
    assert listing.ok
    assert "research/markets/Market-Map.md  [research, 2026]" in listing.output

    read = _run(NoteReadTool(), NoteReadArgs(title="Market Map", folder="research/markets"))
    assert read.ok
    assert "# Market Map" in read.output
    assert "tags: [research, 2026]" in read.output
    assert "[[Competitors]]" in read.output


def test_note_folder_is_sanitized_not_a_traversal() -> None:
    """../../etc must not escape the vault — it's sanitized into a plain
    folder name inside the vault."""
    res = _run(NoteWriteTool(), NoteWriteArgs(
        title="Evil", content="x", folder="../../etc"))
    assert res.ok
    assert ".." not in res.output
    from arenaos.core.config import get_settings
    vault = get_settings().data_dir / "vault"
    # the file must live SOMEWHERE under the vault — never above it
    written = list(vault.rglob("Evil.md"))
    assert len(written) == 1
    assert vault.resolve() in written[0].resolve().parents


def test_backlinks_across_folders_find_real_linkers() -> None:
    w = NoteWriteTool()
    _run(w, NoteWriteArgs(title="Competitors", content="the competition landscape"))
    _run(w, NoteWriteArgs(title="Rival Note",
                          content="compare against [[Competitors]]",
                          folder="deep/nested"))
    _run(w, NoteWriteArgs(title="Unrelated", content="nothing here"))

    bl = _run(NoteBacklinksTool(), NoteBacklinksArgs(title="Competitors"))
    assert bl.ok
    assert "deep/nested/Rival-Note.md" in bl.output
    assert "Unrelated" not in bl.output


def test_backlinks_on_an_orphan_is_an_honest_no() -> None:
    bl = _run(NoteBacklinksTool(), NoteBacklinksArgs(title="Nobody Links To This"))
    assert bl.ok
    assert "no notes link" in bl.output


def test_search_reaches_into_folders() -> None:
    _run(NoteWriteTool(), NoteWriteArgs(
        title="Zebra Analysis", content="zebra crossings pattern", folder="animals"))
    res = _run(NoteSearchTool(), NoteSearchArgs(query="zebra"))
    assert res.ok
    assert "animals/Zebra-Analysis.md" in res.output
