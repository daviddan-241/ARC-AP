"""Memory store + task engine lifecycle tests (deterministic fakes, no model needed)."""
import asyncio

import pytest

from arenaos.core.events import EventBus
from arenaos.engine.engine import BlockingPermission, TaskEngine
from arenaos.memory.store import MemoryStore


def test_memory_crud_and_search():
    store = MemoryStore()
    mid = store.add("long", "Danny likes dark UIs", key="ui-preference")
    assert store.get(mid)["content"] == "Danny likes dark UIs"
    store.add("project", "repo uses FastAPI", key="stack", project_id="p1")
    assert store.update(mid, content="updated")
    assert store.get(mid)["content"] == "updated"
    hits = store.search("fastapi", layer="project")
    assert len(hits) == 1 and "FastAPI" in hits[0]["content"]
    exact = store.search("stack")
    assert exact and exact[0]["key"] == "stack"
    assert store.delete(mid)
    assert store.get(mid) is None


def _engine_with(executor, planner=None, debugger=None):
    async def default_planner(task, ctx):
        return {"steps": []}
    return TaskEngine(bus=EventBus(), planner=planner or default_planner,
                      executor=executor, debugger=debugger, max_retries=3)


def test_task_happy_path_completes():
    async def executor(task, plan, checkpoint):
        return {"summary": "done for real"}

    engine = _engine_with(executor)
    task = engine.create_task("do the thing")

    async def run_and_wait():
        engine.start(task["id"])
        while True:
            row = engine.get(task["id"])
            if row["status"] in ("completed", "failed", "cancelled"):
                return row
            await asyncio.sleep(0.02)

    row = asyncio.run(run_and_wait())
    assert row["status"] == "completed"
    assert row["result"] == "done for real"
    events = engine.get_events(task["id"])
    kinds = [e["kind"] for e in events]
    assert "plan" in kinds and "done" in kinds


def test_task_retry_then_success():
    calls = {"n": 0}

    async def flaky(task, plan, checkpoint):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient failure")
        return {"summary": "third time works"}

    engine = _engine_with(flaky)
    task = engine.create_task("flaky goal")

    async def run_and_wait():
        engine.start(task["id"])
        while True:
            row = engine.get(task["id"])
            if row["status"] in ("completed", "failed", "cancelled"):
                return row
            await asyncio.sleep(0.02)

    row = asyncio.run(run_and_wait())
    assert row["status"] == "completed"
    assert calls["n"] == 3
    assert engine.get(task["id"])["attempts"] >= 2


def test_task_permission_block_then_approve():
    approved = {"flag": False}

    async def executor(task, plan, checkpoint):
        if not approved["flag"]:
            raise BlockingPermission("git.push" if False else
                                     __import__("arenaos.core.permissions", fromlist=["Permission"]).Permission.GIT_PUSH,
                                     "origin")
        return {"summary": "pushed"}

    engine = _engine_with(executor)
    task = engine.create_task("push branch")

    async def scenario():
        engine.start(task["id"])
        for _ in range(200):
            row = engine.get(task["id"])
            if row["status"] == "blocked_on_permission":
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("never blocked")
        approved["flag"] = True
        assert engine.approve(task["id"])
        for _ in range(200):
            row = engine.get(task["id"])
            if row["status"] in ("completed", "failed"):
                return row
            await asyncio.sleep(0.02)
        return engine.get(task["id"])

    row = asyncio.run(scenario())
    assert row["status"] == "completed"


def test_task_cancel():
    started = asyncio.Event()

    async def executor(task, plan, checkpoint):
        started.set()
        await asyncio.sleep(30)
        return {"summary": "never"}

    engine = _engine_with(executor)
    task = engine.create_task("long task")

    async def scenario():
        engine.start(task["id"])
        await started.wait()
        assert engine.cancel(task["id"])
        await asyncio.sleep(0.1)
        return engine.get(task["id"])

    row = asyncio.run(scenario())
    assert row["status"] == "cancelled"
