"""The self-upgrade lab: forging a brand-new tool at runtime, for real.

This proves the actual "if it can't do it in its current form, it upgrades
itself" loop: a capability gap -> lab.forge writes+loads a real tool ->
the new tool is immediately callable -> it survives a fresh process boot
(reloaded from plugins/ like any other plugin).
"""
import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest

from arenaos.lab.forge import ForgeArgs, ForgeTool
from arenaos.plugins.loader import PluginLoader
from arenaos.tools.base import ToolContext, ToolRegistry

WORKING_PLUGIN_CODE = '''
from arenaos.tools.base import BaseTool, ToolResult
from pydantic import BaseModel

class ReverseArgs(BaseModel):
    text: str

class ReverseTool(BaseTool):
    name = "lab.reverse-text"
    description = "Reverse a string (forged capability)."
    args_model = ReverseArgs

    async def execute(self, args, ctx):
        return ToolResult(ok=True, output=args.text[::-1])

def register(context):
    context["state"].tools.register(ReverseTool())
    return {"route": None}
'''

BROKEN_PLUGIN_CODE = '''
def register(context):
    raise RuntimeError("deliberately broken plugin")
'''

NO_REGISTER_TOOLS_CODE = '''
def register(context):
    return {"route": None}
'''


class FakeState:
    def __init__(self, tools):
        self.tools = tools


@pytest.fixture
def plugins_dir():
    d = Path(tempfile.mkdtemp(prefix="lab-plugins-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _forge_ctx(tools_registry):
    state = FakeState(tools_registry)
    return {"app": None, "state": state}, state


def test_forge_writes_loads_and_registers_a_real_new_tool(plugins_dir):
    tools = ToolRegistry()
    forge_context, _ = _forge_ctx(tools)
    forge = ForgeTool(plugins_dir, forge_context)

    args = ForgeArgs(name="reverse-text-lab", description="reverses text",
                     code=WORKING_PLUGIN_CODE)
    result = asyncio.run(forge.execute(args, ToolContext(workspace=".")))

    assert result.ok, result.error
    assert "lab.reverse-text" in result.meta["new_tools"]

    # the forged tool is immediately usable — not just "loaded", actually callable.
    reverse_tool = tools.get("lab.reverse-text")
    call_result = asyncio.run(reverse_tool.execute(
        reverse_tool.args_model(text="hello"), ToolContext(workspace=".")))
    assert call_result.ok and call_result.output == "olleh"

    # persisted to disk exactly like any other plugin.
    assert (plugins_dir / "reverse-text-lab" / "plugin.py").exists()
    assert (plugins_dir / "reverse-text-lab" / "manifest.json").exists()


def test_forged_tool_survives_a_fresh_process_boot(plugins_dir):
    tools = ToolRegistry()
    forge_context, _ = _forge_ctx(tools)
    forge = ForgeTool(plugins_dir, forge_context)
    asyncio.run(forge.execute(
        ForgeArgs(name="reverse-text-lab2", description="x", code=WORKING_PLUGIN_CODE),
        ToolContext(workspace=".")))

    # simulate a full restart: brand-new registry, brand-new loader instance,
    # loading straight from what's on disk in plugins_dir.
    fresh_tools = ToolRegistry()
    fresh_state = FakeState(fresh_tools)
    loader = PluginLoader(plugins_dir)
    loaded = loader.load_all({"app": None, "state": fresh_state})

    assert any(p["name"] == "reverse-text-lab2" and p["status"] == "installed" for p in loaded)
    assert "lab.reverse-text" in [t.name for t in fresh_tools.list()]


def test_forge_never_fakes_success_on_broken_code(plugins_dir):
    tools = ToolRegistry()
    forge_context, _ = _forge_ctx(tools)
    forge = ForgeTool(plugins_dir, forge_context)

    result = asyncio.run(forge.execute(
        ForgeArgs(name="broken-plugin", description="x", code=BROKEN_PLUGIN_CODE),
        ToolContext(workspace=".")))

    assert not result.ok
    assert "deliberately broken plugin" in result.error
    # staged files remain for inspection — nothing pretends this worked.
    assert (plugins_dir / "broken-plugin" / "plugin.py").exists()


def test_forge_reports_when_no_new_tool_was_registered(plugins_dir):
    tools = ToolRegistry()
    forge_context, _ = _forge_ctx(tools)
    forge = ForgeTool(plugins_dir, forge_context)

    result = asyncio.run(forge.execute(
        ForgeArgs(name="lazy-plugin", description="x", code=NO_REGISTER_TOOLS_CODE),
        ToolContext(workspace=".")))

    assert result.ok  # it loaded fine
    assert result.meta["new_tools"] == []
    assert "no new tools registered" in result.output


def test_forge_rejects_bad_slug_and_missing_register(plugins_dir):
    tools = ToolRegistry()
    forge_context, _ = _forge_ctx(tools)
    forge = ForgeTool(plugins_dir, forge_context)

    bad_name = asyncio.run(forge.execute(
        ForgeArgs(name="Not A Slug!", description="x", code=WORKING_PLUGIN_CODE),
        ToolContext(workspace=".")))
    assert not bad_name.ok and "lowercase" in bad_name.error

    no_register = asyncio.run(forge.execute(
        ForgeArgs(name="valid-slug", description="x", code="x = 1"),
        ToolContext(workspace=".")))
    assert not no_register.ok and "register" in no_register.error
