"""Vendored upstream repos: they are the REAL sources, and the integration
tools execute that real code — with honest failures when deps are missing."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from arenaos.tools import integrations as integ
from arenaos.tools.base import ToolContext

VENDOR = Path(__file__).resolve().parent.parent / "vendor"


# ------------------------------------------------ the repos are really there

@pytest.mark.parametrize("rel", [
    "freqtrade/freqtrade/main.py",
    "freqtrade/requirements.txt",
    "gpt-researcher/gpt_researcher/agent.py",
    "gpt-researcher/README.md",
    "TorBot/main.py",
    "TorBot/src/torbot/cli.py",
    "hackingtool/README.md",
    "skills/skills/docx/SKILL.md",
])
def test_vendored_repo_files_are_real(rel):
    assert (VENDOR / rel).exists(), f"vendored file missing: {rel}"


def test_vendored_code_volume_is_substantial():
    """Danny's ask: the repo must genuinely contain the big real codebases —
    not a summary. The four code repos alone are >150k lines."""
    total = 0
    for repo in ("freqtrade", "gpt-researcher", "TorBot", "hackingtool", "skills"):
        for f in (VENDOR / repo).rglob("*.py"):
            total += sum(1 for _ in f.open("rb"))
    assert total > 150_000, f"only {total} python lines vendored — repos incomplete?"


# --------------------------------------------------------- integration tools

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(workspace=str(tmp_path))


def test_freqtrade_backtest_honest_missing_deps(ctx, monkeypatch):
    """Without freqtrade's deps installed the tool must fail loudly with the
    exact install command — never a fake success."""
    tool = integ.FreqtradeBacktestTool()
    res = asyncio.run(tool.execute(
        integ.FreqtradeBacktestArgs(config="x.json", strategy="S"), ctx))
    assert not res.ok
    assert "freqtrade" in res.error
    assert "pip install" in res.error


def test_torbot_honest_missing_deps(ctx):
    tool = integ.TorBotTool()
    res = asyncio.run(tool.execute(
        integ.TorBotArgs(onion="http://example.onion", depth=1), ctx))
    assert not res.ok
    assert "pip install" in res.error


def test_gpt_researcher_honest_missing_deps(ctx):
    tool = integ.GptResearchTool()
    res = asyncio.run(tool.execute(
        integ.GptResearchArgs(query="test"), ctx))
    assert not res.ok
    assert "pip install" in res.error


def test_missing_vendor_dir_fails_fast(tmp_path, monkeypatch):
    monkeypatch.setattr(integ, "VENDOR_DIR", tmp_path / "nowhere")
    with pytest.raises(FileNotFoundError):
        integ._vendor("freqtrade")


def test_all_three_tools_registered_in_real_registry():
    from arenaos.tools.base import ToolRegistry
    reg = ToolRegistry()
    integ.register_integrations(reg)
    names = {t.name for t in reg.list()}
    assert {"freqtrade_backtest", "gpt_research", "torbot_crawl"} <= names
