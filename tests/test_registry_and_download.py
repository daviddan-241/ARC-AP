"""New net/tool-registry additions: real file download, full registry wiring."""
import asyncio

import httpx
import pytest
import respx

from arenaos.browser.session import PersistentBrowser
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import ToolContext
from arenaos.tools.net import DownloadArgs, DownloadFileTool
from arenaos.tools.registry import build_registry


def make_ctx(workspace):
    return ToolContext(workspace=str(workspace))


@respx.mock
def test_download_tool_saves_real_bytes_into_workspace(tmp_path):
    respx.get("https://example.com/file.bin").mock(
        return_value=httpx.Response(200, content=b"real-bytes-here"))
    tool = DownloadFileTool()
    result = asyncio.run(tool.execute(
        DownloadArgs(url="https://example.com/file.bin", path="downloads/file.bin"),
        make_ctx(tmp_path)))
    assert result.ok
    saved = tmp_path / "downloads" / "file.bin"
    assert saved.read_bytes() == b"real-bytes-here"
    assert result.meta["bytes"] == len(b"real-bytes-here")


@respx.mock
def test_download_tool_rejects_jail_escape(tmp_path):
    tool = DownloadFileTool()
    result = asyncio.run(tool.execute(
        DownloadArgs(url="https://example.com/x", path="../../etc/passwd"),
        make_ctx(tmp_path)))
    assert not result.ok
    assert "escapes workspace jail" in result.error


@respx.mock
def test_download_tool_reports_real_http_error(tmp_path):
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
    tool = DownloadFileTool()
    result = asyncio.run(tool.execute(
        DownloadArgs(url="https://example.com/missing", path="x.bin"), make_ctx(tmp_path)))
    assert not result.ok and "404" in result.error


def test_build_registry_wires_every_real_tool(tmp_path):
    sandbox = ExecutionSandbox(base_dir=tmp_path / "ws")
    browser = PersistentBrowser(profile_dir=tmp_path / "profile")
    registry = build_registry(sandbox, browser, tmp_path / "plugins",
                              forge_context={"app": None, "state": None})
    names = {t.name for t in registry.list()}
    for expected in ("shell", "fs.read", "fs.write", "git", "net.http",
                     "net.search", "net.download", "packages.install",
                     "browser", "lab.forge"):
        assert expected in names, f"missing tool: {expected}"
