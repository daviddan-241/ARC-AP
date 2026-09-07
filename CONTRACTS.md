# ARENA-OS — Build Contracts (binding for all module builders)

Repo root: `/app/conversations/6a9e20eb96b96ef98d8e869d/arenaos`

## Runtime facts (do not change)
- Python 3.11, FastAPI + Uvicorn, SQLAlchemy 2 (sync sessions; FastAPI endpoints may run sync in threadpool), Pydantic v2, httpx, cryptography (Fernet), APScheduler, pytest.
- Single modular-monolith process (works on a Render free web service). Background work = asyncio tasks + APScheduler. An optional `worker.py` entrypoint exists for a Render background-worker service that shares the DB.
- UI = dependency-free vanilla ES-module SPA served from `arenaos/ui/static`. No build step.
- Every subsystem is real: no TODOs, no pass-stubs, no simulated results. A tool/action may only report success if the underlying call actually succeeded. Missing external credentials must raise a clear, actionable error — never a fake success.

## Hard rules
1. Only edit files in your assigned module list. Tests go in `tests/test_<module>_*.py`.
2. New DB tables: declare them in `arenaos/db/ext_<yourmodule>.py` importing `Base` from `arenaos.db.models`; expose `def register(engine)` that creates those tables (called from `init_db`).
3. Secrets (API keys, tokens, passwords): resolve from env or the encrypted vault (`arenaos.secrets.manager`). NEVER print, log, return, or store them plaintext. Run all outputs destined for logs/results through the redactor (`arenaos.core.security.redact`).
4. Type hints + docstrings on all public functions. `pytest` green for your module before you finish: `python -m pytest tests/test_<module>_* -x`.
5. Install deps: `pip install -e '/app/conversations/6a9e20eb96b96ef98d8e869d/arenaos[dev]' --quiet` (+ your extras).

## Module ownership map
| Builder | Owns |
|---|---|
| core-infra | `core/logging.py`, `core/security.py`, `db/database.py`, `secrets/manager.py`, `observability/audit.py` |
| arena-layer | `arena/client.py`, `arena/router.py`, `arena/moods.py` |
| executor-tools | `executor/sandbox.py`, `tools/shell.py`, `tools/fs.py`, `tools/process.py`, `tools/net.py`, `tools/browser.py`, `tools/git.py`, `gitmgr/manager.py` |
| memory-engine | `memory/store.py`, `engine/states.py`, `engine/engine.py`, `engine/selfdebug.py` |
| plugins-mcp | `plugins/manager.py`, `plugins/sdk.py`, `plugins/builtin/*.py`, `mcp/client.py` |
| api-layer | `api/app.py`, `api/deps.py`, `api/routers/*.py` |
| ui | `ui/static/**` |
| deploy-scheduler | `deploy/render_client.py`, `deploy/blueprint.py`, `deploy/manager.py`, `scheduler/engine.py`, `notify/channels.py` |

Wave 2 (integrator, do not build): cross-module wiring, end-to-end tests, Dockerfile, render.yaml for ArenaOS itself, docs, git push.

## Core contracts (already written — read before coding)

### Event bus (`core/events.py`)
Topics: `task`, `chat`, `tool`, `exec`, `plugin`, `deploy`, `notify`, `audit`, `log`.
`EventBus.publish(topic, kind, data: dict, task_id: str | None)`. Subscribers get an async iterator. Every state change and tool call publishes here — the audit log, live UI, and SSE streams all consume the same events.

### Permissions (`core/permissions.py`)
`Permission` enum covers: filesystem.read/write/delete, shell.execute, process.start/stop, network.request, browser.use, git.read/write/push, database.read/write, plugin.manage, plugin.invoke, credential.use, memory.read/write, deploy.manage, scheduler.manage, notify.send, settings.manage.
`PermissionPolicy.check(permission, resource) -> Decision` where Decision ∈ {allow, deny, ask_once, ask_task, ask_always}. Policy resolves grants via an injected async provider wired to the `permission_grants` table + UI approval flow. Autonomous mode = default Decision.ALLOW for everything except credential.use (never auto-granted) — configurable in settings.

### Tools (`tools/base.py`)
Every capability is a `BaseTool` subclass: `name`, `description`, `required_permissions: tuple[Permission, ...]`, `args_model: type[BaseModel]`, `async execute(args, ctx: ToolContext) -> ToolResult`. `ToolContext` carries project_id, workspace path, secret-injected env, an emit callback, the policy, and the redactor. `ToolResult` = {ok, output, error, meta(duration_ms, exit_code, files_changed)} and MUST reflect the real outcome.

### Arena model layer (`arena/base.py`)
`ArenaEndpoint` = {name, base_url, path, task_types, priority, default_temperature, max_tokens, protocol ("openai-chat" | "raw-json")}. Endpoints live in `data/arena_endpoints.json` (editable via API/UI). `ModelRouter.route(task_type) -> list[ArenaEndpoint]` returns the ordered fallback chain. `ArenaProvider.complete(...)` / `.stream(...)` — httpx, SSE streaming, retries with backoff, usage extraction. `MOODS` dict (uncensored, high_autonomy, multitask, planner, terminal) = system-prompt presets + temperature guidance passed verbatim to the endpoint — the platform adds no refusal layer of its own. No key present ⇒ `ArenaUnavailableError`; system boots degraded, never fakes a model response.

### Task engine states
`created → planning → queued → running → blocked_on_permission → waiting_retry → debug → {completed | failed | cancelled}`. `Task.checkpoint` (JSON) records completed steps + cursor so `resume()` continues after restart. Self-debug loop: error → read logs → targeted fix callback → rerun, max cycles configurable.

### DB (`db/models.py` — owned by integrator, do not edit)
Tables already defined: users, api_keys, projects, conversations, messages, tasks, task_events, memories, tool_calls, plugins, credentials, audit_log, executions, settings, notifications, deploy_services, scheduled_jobs, permission_grants.

### API surface (api-layer builds this; everyone else respects it)
REST under `/api`: auth, chat (POST message → SSE stream), conversations, tasks (CRUD + start/cancel/resume + SSE), projects, files (list/read/write/delete/upload/download), terminal (WebSocket), plugins, models/endpoints/moods, memory (CRUD + export), logs/audit, settings, deploy, scheduler, notifications. Static UI at `/`. All routes require operator auth (session or API key) except `/healthz` and `/api/auth/login`.

## Definition of done (per module)
Real implementation, real tests passing, no placeholders, secrets redacted everywhere, contract-compliant signatures, and a written report: files created, public API, test output, and any contract gaps found.
