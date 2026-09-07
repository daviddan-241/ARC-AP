"""Autonomous task engine: plan -> execute -> checkpoint -> retry -> self-debug -> resume.

The engine is model-agnostic: `planner`, `executor` and optional `debugger` are
injected async callables, so it is fully testable without any model provider.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

from arenaos.core.events import EventBus
from arenaos.core.logging import get_logger
from arenaos.core.permissions import Permission
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Task, TaskEvent
from arenaos.engine.states import TERMINAL, TaskStatus, valid_transition

logger = get_logger(__name__)

Planner = Callable[[Task, dict], Awaitable[dict]]
Executor = Callable[[Task, dict, dict], Awaitable[dict]]


class BlockingPermission(Exception):
    """Raised by an executor when a permission decision is required."""

    def __init__(self, permission: Permission, resource: str = "") -> None:
        self.permission = permission
        self.resource = resource
        super().__init__(f"permission required: {permission.value} {resource}".strip())


class DebugExhausted(RuntimeError):
    """Self-debug loop hit its cycle cap."""


class TaskEngine:
    """Persisted state machine running concurrent, checkpointed, retried tasks."""

    def __init__(self, session_factory=None, bus: Optional[EventBus] = None,
                 planner: Optional[Planner] = None, executor: Optional[Executor] = None,
                 debugger: Optional[Callable] = None, max_retries: int = 3,
                 max_concurrency: int = 4, max_debug_cycles: int = 3,
                 retry_backoff_base: float = 1.5) -> None:
        self._sessions = session_factory or get_sessionmaker()
        self._bus = bus or EventBus()
        self._planner = planner
        self._executor = executor
        self._debugger = debugger
        self.max_retries = max_retries
        self.max_debug_cycles = max_debug_cycles
        self.backoff = retry_backoff_base
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._running: dict[str, asyncio.Task] = {}
        self._pending: dict[str, BlockingPermission] = {}
        self._resume: dict[str, asyncio.Event] = {}

    # -- persistence helpers -------------------------------------------------

    def _update(self, task_id: str, **fields: Any) -> None:
        session = self._sessions()
        try:
            row = session.get(Task, task_id)
            if row is None:
                raise KeyError(f"unknown task {task_id}")
            if "status" in fields:
                target = TaskStatus(fields["status"])
                source = TaskStatus(row.status)
                if source not in TERMINAL and not valid_transition(source, target):
                    raise ValueError(f"illegal transition {source.value} -> {target.value}")
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()
        finally:
            session.close()

    def _add_event(self, task_id: str, kind: str, data: dict) -> None:
        session = self._sessions()
        try:
            row = session.get(Task, task_id)
            seq = (row.events[-1].seq + 1) if row and row.events else 0
            session.add(TaskEvent(task_id=task_id, seq=seq, kind=kind, data=data))
            session.commit()
        finally:
            session.close()

    async def _publish(self, kind: str, data: dict, task_id: Optional[str] = None) -> None:
        try:
            await self._bus.publish("task", kind, data, task_id=task_id)
        except Exception:
            logger.exception("event publish failed")

    # -- public API ----------------------------------------------------------

    def create_task(self, goal: str, project_id: Optional[str] = None,
                    task_type: str = "general", mode: str = "autonomous",
                    parent_id: Optional[str] = None, priority: int = 0) -> dict:
        """Create a persisted task in CREATED state."""
        task_id = uuid.uuid4().hex[:12]
        session = self._sessions()
        try:
            session.add(Task(id=task_id, project_id=project_id, parent_id=parent_id,
                             goal=goal, task_type=task_type, mode=mode,
                             status=TaskStatus.CREATED.value, priority=priority))
            session.commit()
        finally:
            session.close()
        try:
            asyncio.get_running_loop()
            asyncio.ensure_future(self._publish("created", {"goal": goal}, task_id))
        except RuntimeError:
            pass  # no running loop (sync context) — event is persisted in the DB anyway
        return {"id": task_id, "status": TaskStatus.CREATED.value}

    def start(self, task_id: str) -> bool:
        """Schedule the task's asyncio coroutine. Returns False if already running/terminal."""
        current = self.get(task_id)
        if current is None:
            raise KeyError(f"unknown task {task_id}")
        if task_id in self._running and not self._running[task_id].done():
            return False
        if TaskStatus(current["status"]) in TERMINAL and current["status"] != TaskStatus.CREATED.value:
            return False
        self._running[task_id] = asyncio.create_task(self._run(task_id))
        return True

    async def _run(self, task_id: str) -> None:
        """The full lifecycle loop: plan, execute, checkpoint, retry, debug."""
        async with self._semaphore:
            await self._publish("started", {}, task_id)
            self._update(task_id, status=TaskStatus.PLANNING.value,
                         started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
            self._add_event(task_id, "plan_start", {})
            plan = {}
            if self._planner:
                try:
                    task = self._get(task_id)
                    plan = await self._planner(task, {}) or {}
                except Exception as exc:
                    error_text = f"planner failed: {type(exc).__name__}: {exc}"
                    self._update(task_id, status=TaskStatus.FAILED.value, error=error_text,
                                 finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
                    self._add_event(task_id, "error", {"error": error_text})
                    await self._publish("failed", {"error": error_text}, task_id)
                    return
            self._update(task_id, status=TaskStatus.QUEUED.value, plan=plan)
            self._add_event(task_id, "plan", {"plan": plan})
            await self._publish("plan", {"plan": plan}, task_id)

            checkpoint: dict = {"step": 0, "plan": plan, "results": [], "attempts": 0}
            self._update(task_id, status=TaskStatus.RUNNING.value, checkpoint=checkpoint)

            debug_cycles = 0
            while True:
                if TaskStatus(self._get(task_id)["status"]) == TaskStatus.CANCELLED:
                    return
                try:
                    task = self._get(task_id)
                    result = await self._executor(task, plan, checkpoint)
                    self._update(task_id, status=TaskStatus.COMPLETED.value,
                                 result=result.get("summary", ""),
                                 finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
                    self._add_event(task_id, "done", {"result": result})
                    await self._publish("completed", {"result": result}, task_id)
                    return
                except BlockingPermission as blocked:
                    self._pending[task_id] = blocked
                    self._update(task_id, status=TaskStatus.BLOCKED_ON_PERMISSION.value,
                                 error=f"awaiting permission: {blocked.permission.value}")
                    self._add_event(task_id, "permission_block",
                                    {"permission": blocked.permission.value, "resource": blocked.resource})
                    await self._publish("blocked_on_permission",
                                        {"permission": blocked.permission.value,
                                         "resource": blocked.resource}, task_id)
                    event = asyncio.Event()
                    self._resume[task_id] = event
                    await event.wait()
                    self._resume.pop(task_id, None)
                    row = self._get(task_id)
                    if TaskStatus(row["status"]) == TaskStatus.CANCELLED:
                        return
                    self._update(task_id, status=TaskStatus.RUNNING.value)
                except asyncio.CancelledError:
                    self._update(task_id, status=TaskStatus.CANCELLED.value)
                    await self._publish("cancelled", {}, task_id)
                    raise
                except Exception as exc:
                    checkpoint["attempts"] = checkpoint.get("attempts", 0) + 1
                    row = self._get(task_id)
                    attempts = row.get("attempts", 0) + 1
                    error_text = f"{type(exc).__name__}: {exc}"
                    self._add_event(task_id, "error", {"error": error_text, "attempt": attempts})
                    await self._publish("error", {"error": error_text, "attempt": attempts}, task_id)
                    if attempts <= row.get("max_retries", self.max_retries):
                        self._update(task_id, attempts=attempts, error=error_text,
                                     status=TaskStatus.WAITING_RETRY.value, checkpoint=checkpoint)
                        await asyncio.sleep(self.backoff ** attempts)
                        self._update(task_id, status=TaskStatus.RUNNING.value)
                        continue
                    if self._debugger and debug_cycles < self.max_debug_cycles:
                        debug_cycles += 1
                        self._update(task_id, status=TaskStatus.DEBUG.value, error=error_text)
                        try:
                            fix = await self._debugger(self._get(task_id), error_text, checkpoint)
                        except Exception as dbg_exc:
                            self._update(task_id, status=TaskStatus.FAILED.value,
                                         error=f"{error_text}; debugger failed: {dbg_exc}",
                                         finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
                            await self._publish("failed", {"error": error_text}, task_id)
                            return
                        self._add_event(task_id, "debug_fix", {"cycle": debug_cycles, "fix": str(fix)[:2000]})
                        await self._publish("debug", {"cycle": debug_cycles}, task_id)
                        self._update(task_id, status=TaskStatus.RUNNING.value, attempts=0)
                        continue
                    self._update(task_id, status=TaskStatus.FAILED.value, error=error_text,
                                 finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
                    await self._publish("failed", {"error": error_text}, task_id)
                    return

    def approve(self, task_id: str) -> bool:
        """Resolve a permission block and resume the task."""
        self._pending.pop(task_id, None)
        event = self._resume.get(task_id)
        if event:
            event.set()
            return True
        return False

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task. Returns True if cancellation took effect."""
        row = self._get(task_id)
        if row is None or TaskStatus(row["status"]) in TERMINAL:
            return False
        if TaskStatus(row["status"]) == TaskStatus.BLOCKED_ON_PERMISSION:
            self._update(task_id, status=TaskStatus.CANCELLED.value)
            event = self._resume.get(task_id)
            if event:
                event.set()
            return True
        handle = self._running.get(task_id)
        if handle and not handle.done():
            handle.cancel()
            return True
        self._update(task_id, status=TaskStatus.CANCELLED.value)
        return True

    def resume(self, task_id: str) -> bool:
        """Restart a task from its checkpoint."""
        row = self._get(task_id)
        if row is None:
            return False
        if TaskStatus(row["status"]) not in (TaskStatus.FAILED, TaskStatus.WAITING_RETRY):
            return False
        self._update(task_id, status=TaskStatus.QUEUED.value)
        return self.start(task_id)

    def _get(self, task_id: str) -> Optional[dict]:
        session = self._sessions()
        try:
            row = session.get(Task, task_id)
            if row is None:
                return None
            return {"id": row.id, "goal": row.goal, "task_type": row.task_type,
                    "mode": row.mode, "status": row.status, "plan": row.plan,
                    "checkpoint": row.checkpoint, "result": row.result, "error": row.error,
                    "attempts": row.attempts, "max_retries": row.max_retries,
                    "project_id": row.project_id}
        finally:
            session.close()

    def get(self, task_id: str) -> Optional[dict]:
        return self._get(task_id)

    def get_events(self, task_id: str) -> list[dict]:
        session = self._sessions()
        try:
            row = session.get(Task, task_id)
            if row is None:
                return []
            return [{"seq": e.seq, "kind": e.kind, "data": e.data,
                     "ts": e.created_at.isoformat() if e.created_at else None}
                    for e in row.events]
        finally:
            session.close()

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        session = self._sessions()
        try:
            q = session.query(Task).order_by(Task.created_at.desc())
            if status:
                q = q.filter(Task.status == status)
            return [{"id": r.id, "goal": r.goal, "status": r.status,
                     "task_type": r.task_type, "mode": r.mode,
                     "project_id": r.project_id, "error": r.error,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in q.limit(limit).all()]
        finally:
            session.close()
