"""FastAPI application factory: wires every real subsystem into app.state."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from arenaos.api.routers import auth as auth_router
from arenaos.api.routers import chat as chat_router
from arenaos.api.routers import core as core_router
from arenaos.api.routers import tasks as tasks_router
from arenaos.arena.base import ArenaEndpoint, ChatMessage, CompleteRequest, MOODS
from arenaos.browser.session import PersistentBrowser
from arenaos.core.config import get_settings
from arenaos.core.events import EventBus
from arenaos.core.logging import get_logger, setup_logging
from arenaos.db.database import init_db, seed
from arenaos.engine.agent_loop import MaxStepsExceeded, run_agent_loop
from arenaos.engine.engine import TaskEngine
from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import ToolContext
from arenaos.memory.autolearn import AutoLearner
from arenaos.plugins.loader import load_plugins
from arenaos.tools.registry import build_registry
from arenaos.memory.store import MemoryStore
from arenaos.observability.audit import Audit
from arenaos.secrets.manager import SecretsManager

logger = get_logger(__name__)

TEST_MODE = os.environ.get("ARENAOS_TEST") == "1"


def _build_arena_provider(app: FastAPI):
    """Create the arena.ai web-session provider if Playwright is installed. Honest if not."""
    if TEST_MODE:
        return None
    try:
        from arenaos.arena.web_provider import (ArenaWebSessionProvider,
                                                WebSessionConfig)
        provider = ArenaWebSessionProvider(
            WebSessionConfig(),
            get_credential=lambda name: _safe_credential(app, name),
        )
        logger.info("arena web-session provider created (browser launches lazily)")
        return provider
    except Exception as exc:
        logger.warning("arena web provider unavailable: %s", exc)
        return None


def _safe_credential(app: FastAPI, name: str) -> Optional[str]:
    try:
        return SecretsManager().get(name)
    except Exception:
        return None


def _build_engine(app: FastAPI) -> TaskEngine:
    """Task engine whose executor runs the REAL tool-using agent loop — shell,
    filesystem, git, browser, downloads, package installs, and lab.forge for
    self-upgrade are all genuinely available to every task, not just a raw
    chat completion."""
    provider = app.state.provider

    async def planner(task: dict, _context: dict) -> dict:
        return {"goal": task["goal"], "approach": "tool_loop"}

    async def executor(task: dict, plan: dict, checkpoint: dict) -> dict:
        if provider is None:
            raise RuntimeError("no model provider available (arena transport not initialized)")

        async def complete_fn(transcript: list[dict[str, str]]) -> str:
            messages = [ChatMessage(role=m["role"], content=m["content"]) for m in transcript]
            request = CompleteRequest(
                endpoint=ArenaEndpoint(name="arena-web", base_url="https://arena.ai"),
                messages=messages,
            )
            response = await provider.complete(request)
            return response.content

        ws = app.state.sandbox.create_workspace(task.get("project_id") or task["id"])
        ctx = ToolContext(workspace=str(ws), project_id=task.get("project_id"),
                          task_id=task["id"], env=app.state.secrets.inject_env())
        try:
            result = await run_agent_loop(
                goal=task["goal"], registry=app.state.tools, ctx=ctx,
                complete=complete_fn, mood_prelude=MOODS["uncensored"]["system_prelude"],
            )
        except MaxStepsExceeded as exc:
            raise RuntimeError(str(exc)) from exc
        return {"summary": result["summary"], "model": "arena-web",
                "tool_calls": result["tool_calls"]}

    return TaskEngine(bus=app.state.bus, planner=planner, executor=executor)


def create_app() -> FastAPI:
    """Build the ArenaOS application with all subsystems wired."""
    setup_logging()
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    seed()

    app = FastAPI(title="ArenaOS", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.bus = EventBus()
    app.state.sandbox = ExecutionSandbox()
    app.state.browser = PersistentBrowser()
    app.state.memory = MemoryStore()
    app.state.autolearn = AutoLearner(app.state.memory)
    app.state.secrets = SecretsManager()
    app.state.audit = Audit(bus=app.state.bus)
    app.state.provider = None
    app.state.engine = None

    # Real tool registry — the agent's actual capabilities (shell, fs, git,
    # browser, net, package installs, lab.forge for self-upgrade). Built BEFORE
    # plugins load so a forged tool from a prior session can re-register on boot.
    app.state.tools = build_registry(
        sandbox=app.state.sandbox, browser=app.state.browser,
        plugins_dir=Path(__file__).parent.parent.parent / "plugins",
        forge_context={"app": app, "state": app.state},
    )

    if settings.arena_transport == "web":
        app.state.provider = _build_arena_provider(app)
    app.state.engine = _build_engine(app)

    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(tasks_router.router)
    app.include_router(core_router.router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        degraded = settings.arena_transport == "web" and app.state.provider is None
        return JSONResponse({"status": "ok", "degraded": degraded,
                             "transport": settings.arena_transport})

    # Real plugin system: every plugins/<name>/ with manifest + register() loads
    # here; a broken plugin is recorded with status=error and skipped.
    app.state.plugins = load_plugins({"app": app, "state": app.state})

    # Static UI mount goes LAST so real routes always win over the catch-all.
    static_dir = Path(__file__).parent.parent / "ui" / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")

    return app


app = create_app()
