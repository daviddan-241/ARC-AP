"""Real integrations with the vendored upstream repos.

vendor/ contains the ACTUAL upstream sources (freqtrade, gpt-researcher,
TorBot, anthropic skills). These tools execute that real code end-to-end
via subprocess — no shims, no re-implementations. When a repo's pip
dependencies aren't installed in the current environment, the tool fails
loudly and prints the exact install command (never a fake success).
"""
from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field

from arenaos.core.config import get_settings
from arenaos.core.logging import get_logger
from arenaos.tools.base import BaseTool, Permission, ToolContext, ToolResult

logger = get_logger(__name__)

VENDOR_DIR = Path(__file__).resolve().parent.parent.parent / "vendor"
RUN_TIMEOUT_S = 300  # subprocess cap; long jobs belong in background tasks


def _vendor(name: str) -> Path:
    path = VENDOR_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"vendored repo 'vendor/{name}' is missing — it ships with the repo")
    return path


async def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run a real subprocess with a hard timeout; stream nothing, capture all."""
    import os
    proc_env = dict(os.environ)
    if env:
        proc_env.update(env)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd), env=proc_env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=RUN_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            return 124, "process exceeded timeout — run it as a background task instead"
        return proc.returncode or 0, out.decode("utf-8", "replace")[:8000]
    except FileNotFoundError as exc:
        return 127, f"executable not found ({exc}) — install the repo's requirements first"


def _missing_deps_error(repo: str, hint: str) -> str:
    return (f"{repo} dependencies not installed in this environment. "
            f"Install for real with: {hint}")


# --------------------------------------------------------------- freqtrade

class FreqtradeBacktestArgs(BaseModel):
    config: str = Field(description="Path to a freqtrade config JSON (absolute or relative to the workdir)")
    strategy: str = Field(default="Strategy002",
                          description="Name of the strategy class inside user_data/strategies to backtest")
    timerange: Optional[str] = Field(default=None,
                                     description="Timerange to test, e.g. '20240101-' or '20250101-20250601'")
    pairs: Optional[str] = Field(default=None, description="Comma-separated pair list override, e.g. 'BTC/USDT,ETH/USDT'")
    timeframe: Optional[str] = Field(default=None, description="Candle timeframe override, e.g. '5m', '1h'")


class FreqtradeBacktestTool(BaseTool):
    """Run a REAL freqtrade backtest using the vendored freqtrade source."""
    name: ClassVar[str] = "freqtrade_backtest"
    description: ClassVar[str] = (
        "Run a real crypto-strategy backtest with freqtrade (vendored source in "
        "vendor/freqtrade). Requires freqtrade's pip deps installed; returns the "
        "real backtest report — profit %, trades, drawdown, Sharpe.")
    required_permissions: ClassVar[list[Permission]] = [Permission.SHELL_EXECUTE]

    args_model = FreqtradeBacktestArgs

    async def execute(self, args: FreqtradeBacktestArgs, ctx: ToolContext) -> ToolResult:
        repo = _vendor("freqtrade")
        cmd = [sys.executable, "-m", "freqtrade", "backtesting",
               "--config", args.config, "--strategy", args.strategy]
        if args.timerange:
            cmd += ["--timerange", args.timerange]
        if args.pairs:
            cmd += ["--pairs", args.pairs]
        if args.timeframe:
            cmd += ["--timeframe", args.timeframe]
        # Run from the vendored repo dir — `python -m freqtrade` resolves the
        # vendored package from cwd; its pip deps must be installed for real.
        code, out = await _run(cmd, repo)
        if code == 0:
            return ToolResult(ok=True, output=out)
        if "ModuleNotFoundError" in out or code == 127:
            return ToolResult(ok=False, error=_missing_deps_error(
                "freqtrade", "pip install -r vendor/freqtrade/requirements.txt "
                "&& pip install -e vendor/freqtrade"))
        return ToolResult(ok=False, error=f"backtest exited {code}:\n{out}")


# ----------------------------------------------------------- gpt-researcher

class GptResearchArgs(BaseModel):
    query: str = Field(description="The research question to investigate")
    report_type: str = Field(default="research_report",
                             description="gpt-researcher report type: research_report, resource_report, outline_report, contrast_report")
    max_sources: int = Field(default=8, ge=2, le=25, description="Source budget for the run")


class GptResearchTool(BaseTool):
    """Run the REAL vendored gpt-researcher agent to produce a cited report."""
    name: ClassVar[str] = "gpt_research"
    description: ClassVar[str] = (
        "Run the vendored gpt-researcher agent (vendor/gpt-researcher) for "
        "plan-and-solve web research with citations. Needs its pip deps and a "
        "configured LLM provider; returns the real generated report.")
    required_permissions: ClassVar[list[Permission]] = [Permission.NETWORK_REQUEST]

    args_model = GptResearchArgs

    async def execute(self, args: GptResearchArgs, ctx: ToolContext) -> ToolResult:
        repo = _vendor("gpt-researcher")
        # The real programmatic entrypoint from the repo's docs:
        # from gpt_researcher import GPTResearcher; await researcher.run()
        driver = (
            "import asyncio\n"
            "from gpt_researcher import GPTResearcher\n\n"
            f"async def main():\n"
            f"    r = GPTResearcher(query={shlex.quote(args.query)!r}, "
            f"report_type={shlex.quote(args.report_type)!r})\n"
            "    await r.conduct_research()\n"
            "    report = await r.write_report()\n"
            "    print(report)\n\n"
            "asyncio.run(main())\n"
        )
        code, out = await _run([sys.executable, "-c", driver], repo)
        if code == 0:
            return ToolResult(ok=True, output=out)
        if "ModuleNotFoundError" in out or code == 127:
            return ToolResult(ok=False, error=_missing_deps_error(
                "gpt-researcher",
                "pip install -e 'vendor/gpt-researcher[langgraph]' "
                "(see vendor/gpt-researcher/README.md)"))
        return ToolResult(ok=False, error=f"gpt-researcher exited {code}:\n{out}")


# ------------------------------------------------------------------ TorBot

class TorBotArgs(BaseModel):
    onion: str = Field(description="The .onion (or clearnet) URL to crawl")
    depth: int = Field(default=0, ge=0, le=3, description="How many link levels to follow")
    extract: bool = Field(default=False, description="Extract emails/descriptions from pages")


class TorBotTool(BaseTool):
    """Crawl onion sites with the REAL vendored TorBot engine."""
    name: ClassVar[str] = "torbot_crawl"
    description: ClassVar[str] = (
        "Crawl a .onion site with the vendored TorBot (vendor/TorBot) — "
        "onion link trees, emails, metadata. Requires Tor (SOCKS 9050) and "
        "TorBot's pip deps; returns real crawl output.")
    required_permissions: ClassVar[list[Permission]] = [Permission.NETWORK_REQUEST]

    args_model = TorBotArgs

    async def execute(self, args: TorBotArgs, ctx: ToolContext) -> ToolResult:
        repo = _vendor("TorBot")
        # The repo's real entrypoint: main.py -> torbot.cli, src-layout import
        cmd = [sys.executable, "main.py", "--url", args.onion,
               "--depth", str(args.depth), "--quiet", "--visualize", "json"]
        code, out = await _run(cmd, repo, env={"PYTHONPATH": str(repo / "src")})
        if code == 0:
            return ToolResult(ok=True, output=out)
        if "ModuleNotFoundError" in out or code == 127:
            return ToolResult(ok=False, error=_missing_deps_error(
                "TorBot", "pip install -r vendor/TorBot/requirements.txt"))
        return ToolResult(ok=False, error=f"torbot exited {code}:\n{out}")


def register_integrations(registry) -> None:
    """Wire the vendored-repo tools into the registry (called at startup)."""
    registry.register(FreqtradeBacktestTool())
    registry.register(GptResearchTool())
    registry.register(TorBotTool())
