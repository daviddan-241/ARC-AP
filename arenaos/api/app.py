"""FastAPI application factory: wires every real subsystem into app.state."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from arenaos.api.routers import auth as auth_router
from arenaos.api.routers import chat as chat_router
from arenaos.api.routers import core as core_router
from arenaos.api.routers import live_browser as live_browser_router
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
            browser=app.state.browser,  # shared Chromium — see create_app()
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


def _task_engine_complete(provider):
    """Build the single complete() used across chat, tasks and sub-agents."""
    from arenaos.arena.base import ArenaEndpoint, ChatMessage, CompleteRequest

    async def complete_fn(transcript: list[dict[str, str]]) -> str:
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in transcript]
        request = CompleteRequest(
            endpoint=ArenaEndpoint(name="arena-web", base_url="https://arena.ai"),
            messages=messages,
        )
        response = await provider.complete(request)
        return response.content

    return complete_fn


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
    # ONE Chromium for the whole app: the arena.ai model tab, the agent's
    # webmail tab, AND the operator's free browsing all live in this single
    # persistent context on the ARENA profile dir (where the arena.ai login
    # already lives). Real fix for the free-tier OOM: two separate Chromium
    # launches (~300-500MB each) on a 512MB host got the process killed,
    # which is what wiped the arena.ai login and made it ask for the email
    # again after every restart. One launch, one profile, login survives.
    try:
        from arenaos.arena.web_provider import WebSessionConfig as _WSC
        _shared_profile = Path(_WSC().browser_profile_dir)
    except Exception:
        _shared_profile = None
    app.state.browser = PersistentBrowser(profile_dir=_shared_profile)
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
    # The one complete fn (arena.ai via the logged-in web session) — used by
    # chat, the task engine, AND agent_spawn sub-agents. One model does all.
    app.state.complete_fn = (_task_engine_complete(app.state.provider)
                             if app.state.provider else None)
    app.state.engine = _build_engine(app)

    # Seed the builtin skill library into the data dir (first boot only).
    import shutil as _shutil
    _builtin = Path(__file__).parent.parent / "skills" / "builtin"
    _dest = Path(settings.data_dir) / "skills"
    if _builtin.exists():
        _dest.mkdir(parents=True, exist_ok=True)
        for _sk in _builtin.iterdir():
            if _sk.is_dir() and not (_dest / _sk.name).exists():
                _shutil.copytree(_sk, _dest / _sk.name)

    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(tasks_router.router)
    app.include_router(core_router.router)
    app.include_router(live_browser_router.router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        degraded = settings.arena_transport == "web" and app.state.provider is None
        return JSONResponse({"status": "ok", "degraded": degraded,
                             "transport": settings.arena_transport})

    # Real plugin system: every plugins/<name>/ with manifest + register() loads
    # here; a broken plugin is recorded with status=error and skipped.
    app.state.plugins = load_plugins({"app": app, "state": app.state})

    # Static UI mount goes LAST so real routes always win over the catch-all.
    # The React build (ui-react/dist) wins when present — real SPA fallback so
    # client-side routes (/chat, /skills, /library…) deep-link correctly.
    react_dist = Path(__file__).parent.parent.parent / "ui-react" / "dist"
    if (react_dist / "index.html").is_file():

        @app.get("/", include_in_schema=False)
        async def react_home() -> FileResponse:
            return FileResponse(str(react_dist / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def react_spa(full_path: str) -> FileResponse:
            """Serve real files when they exist; otherwise the SPA shell so
            client-side routes (/chat, /skills, /library…) deep-link correctly."""
            if full_path.startswith(("api/", "ws/")):
                raise HTTPException(status_code=404)
            if full_path and not full_path.startswith(".."):
                candidate = (react_dist / full_path).resolve()
                if str(candidate).startswith(str(react_dist.resolve())) and candidate.is_file():
                    return FileResponse(str(candidate))
            return FileResponse(str(react_dist / "index.html"))
    else:
        static_dir = Path(__file__).parent.parent / "ui" / "static"
        if static_dir.is_dir():
            app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")

    return app


app = create_app()
