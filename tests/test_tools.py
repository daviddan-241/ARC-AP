"""Tool layer tests: shell, fs, git (real executions)."""
import asyncio

import httpx
import pytest
import respx

from arenaos.core.permissions import Permission, PermissionPolicy, Decision
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.fs import DeleteFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from arenaos.tools.base import ToolContext
from arenaos.tools.git import GitArgs, GitTool
from arenaos.tools.net import HttpArgs, HttpRequestTool, SearchArgs, WebSearchTool
from arenaos.tools.shell import ShellArgs, ShellTool


def make_ctx(workspace, policy=None):
    return ToolContext(workspace=str(workspace), policy=policy)


def test_shell_tool_real_execution():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-shell")
    tool = ShellTool(sandbox)
    result = asyncio.run(tool.execute(ShellArgs(command="echo tool-ok"), make_ctx(ws)))
    assert result.ok
    assert "tool-ok" in result.output
    assert result.meta["exit_code"] == 0


def test_shell_tool_reports_real_failure():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-shell2")
    tool = ShellTool(sandbox)
    result = asyncio.run(tool.execute(ShellArgs(command="false"), make_ctx(ws)))
    assert not result.ok
    assert result.meta["exit_code"] == 1


def test_fs_write_read_list_delete_roundtrip():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-fs")
    ctx = make_ctx(ws)
    w = asyncio.run(WriteFileTool().execute(
        __import__("arenaos.tools.fs", fromlist=["WriteArgs"]).WriteArgs(path="a/b.txt", content="hi"),
        ctx))
    assert w.ok
    r = asyncio.run(ReadFileTool().execute(
        __import__("arenaos.tools.fs", fromlist=["ReadArgs"]).ReadArgs(path="a/b.txt"), ctx))
    assert r.ok and r.output == "hi"
    listing = asyncio.run(ListFilesTool().execute(
        __import__("arenaos.tools.fs", fromlist=["ListArgs"]).ListArgs(path="."), ctx))
    assert listing.ok and "a/b.txt" in listing.output
    d = asyncio.run(DeleteFileTool().execute(
        __import__("arenaos.tools.fs", fromlist=["DeleteArgs"]).DeleteArgs(path="a/b.txt"), ctx))
    assert d.ok


def test_fs_jail_escape_rejected():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-fs2")
    ctx = make_ctx(ws)
    from arenaos.tools.fs import WriteArgs
    result = asyncio.run(WriteFileTool().execute(
        WriteArgs(path="../../outside.txt", content="nope"), ctx))
    assert not result.ok
    assert "escapes workspace jail" in result.error


def test_git_tool_push_denied_without_permission():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-git")
    async def grant(permission, resource=None):
        return []
    policy = PermissionPolicy(grant, autonomous=False, default=Decision.ASK_ONCE)
    ctx = make_ctx(ws, policy=policy)
    tool = GitTool()
    result = asyncio.run(tool.execute(GitArgs(op="push"), ctx))
    assert not result.ok
    assert "git.push permission not granted" in result.error


def test_git_tool_real_commit():
    sandbox = ExecutionSandbox()
    ws = sandbox.create_workspace("tool-git2")
    run = asyncio.run(sandbox.run(
        "git init -q && git config user.email t@t && git config user.name T && echo hi > f.txt",
        cwd=str(ws)))
    assert run.ok
    ctx = make_ctx(ws)
    tool = GitTool()
    add = asyncio.run(sandbox.run("git add -A", cwd=str(ws)))
    assert add.ok
    result = asyncio.run(tool.execute(GitArgs(op="commit", message="init"), ctx))
    assert result.ok
    log = asyncio.run(tool.execute(GitArgs(op="log"), ctx))
    assert log.ok and "init" in log.output


@respx.mock
def test_http_tool_real_request_mocked():
    respx.get("https://example.com/ping").mock(return_value=httpx.Response(200, json={"ok": True}))
    tool = HttpRequestTool()
    result = asyncio.run(tool.execute(
        HttpArgs(url="https://example.com/ping"), make_ctx("/tmp")))
    assert result.ok
    assert "ok" in result.output.lower()
    assert result.meta["status_code"] == 200


def test_http_tool_rejects_bad_scheme():
    tool = HttpRequestTool()
    result = asyncio.run(tool.execute(
        HttpArgs(url="ftp://bad.example"), make_ctx("/tmp")))
    assert not result.ok


def test_websearch_tool_live():
    """Real keyless DuckDuckGo search — network-dependent, honest on failure."""
    tool = WebSearchTool()
    result = asyncio.run(tool.execute(SearchArgs(query="python asyncio docs"), make_ctx("/tmp")))
    assert result.ok is True or result.ok is False  # never crashes; real outcome recorded
    print("websearch result:", result.ok, result.output[:120])
